from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings
from pgvector.django import L2Distance

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from .models import PolicyFile, PolicyDocument
from .serializers import PolicyFileSerializer

class PolicyFileListCreateView(generics.ListCreateAPIView):
    """
    API endpoint that allows policy files to be viewed or edited.
    """
    serializer_class = PolicyFileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        # If superuser, can see all. Otherwise, filter by organization
        if user.is_superuser:
            return PolicyFile.objects.all()
        if user.organization:
            return PolicyFile.objects.filter(organization=user.organization)
        return PolicyFile.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        org = user.organization
        
        save_kwargs = {'uploaded_by': user}
        
        # If organization is not provided in data, use user's organization
        if not serializer.validated_data.get('organization'):
            if org:
                save_kwargs['organization'] = org
                
        serializer.save(**save_kwargs)
        
        # PROACTIVE: Process the file immediately while we have it in memory/temp
        try:
            from .services import PolicyProcessingService
            service = PolicyProcessingService()
            file_obj = self.request.FILES.get('file')
            if file_obj:
                # Read content and process
                file_obj.seek(0)
                content = file_obj.read()
                # Create a background-like processing but immediate for this request
                # Use instance to update its status
                instance = serializer.instance
                service.process_file_content(instance, content, instance.file.public_id)
                print(f"✅ Proactively processed file: {instance.title}")
        except Exception as e:
            print(f"⚠️ Proactive processing failed: {str(e)}")
            # Fallback to background processing (signals already handle this)
            pass

class PolicyFileRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint that allows a policy file to be retrieved, updated or deleted.
    """
    serializer_class = PolicyFileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return PolicyFile.objects.all()
        if user.organization:
            return PolicyFile.objects.filter(organization=user.organization)
        return PolicyFile.objects.none()

    def perform_destroy(self, instance):
        # Trigger Cloudinary deletion
        from .services import PolicyProcessingService
        service = PolicyProcessingService()
        service.delete_policy_file(instance)
        # Model deletion (chunks will be deleted via CASCADE)
        instance.delete()

class PolicyQAView(APIView):
    """
    API endpoint for asking questions about policies.
    Expects 'query' in request data.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        query = request.data.get('query')
        organization_id = request.data.get('organization_id')
        
        if not query:
            return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Default to user's organization if not provided
        if not organization_id and request.user.organization:
            organization_id = request.user.organization.id
            
        try:
            # Generate embedding for the query
            embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
            query_embedding = embeddings.embed_query(query)
            
            # Semantic search using pgvector
            # Filter by organization if applicable
            search_qs = PolicyDocument.objects.all()
            if organization_id:
                search_qs = search_qs.filter(policy_file__organization_id=organization_id)
                
            # Get top 5 most similar chunks
            # Using L2Distance (Euclidean) - smaller is closer
            # Note: For normalized vectors (OpenAI), Cosine and L2 are related.
            similar_docs = search_qs.annotate(
                distance=L2Distance('embedding', query_embedding)
            ).order_by('distance')[:5]
            
            if not similar_docs:
                return Response({
                    'answer': "I couldn't find any policy documents for your organization. Please ensure policies are uploaded and processed.",
                    'sources': []
                })

            # Prepare context
            context_text = "\n\n".join([doc.content for doc in similar_docs])
            
            # Generate answer using LLM
            llm = ChatOpenAI(
                model_name="gpt-4o", 
                temperature=0, 
                openai_api_key=settings.OPENAI_API_KEY
            )
            
            template = """You are a helpful HR assistant. Answer the question based ONLY on the following context:
            {context}
            
            Question: {question}
            
            If the answer is not in the context, say "I don't have enough information in the provided policies to answer that."
            Do not hallucinate or use outside knowledge.

            FORMATTING: If you find an answer, wrap the most important part of the policy in:
            [INSIGHT_CARD] title: {Policy Name} | message: {The core policy details} | type: info | topic: Policy [/INSIGHT_CARD]
            """
            
            prompt = ChatPromptTemplate.from_template(template)
            chain = prompt | llm | StrOutputParser()
            
            answer = chain.invoke({
                "context": context_text,
                "question": query
            })
            
            # Collect sources
            sources = [
                {
                    'title': doc.title,
                    'file_id': doc.policy_file.id if doc.policy_file else None,
                    'score': float(doc.distance) if hasattr(doc, 'distance') else None
                } 
                for doc in similar_docs
            ]
            
            return Response({
                'answer': answer,
                'sources': sources,
                'context_used': context_text[:200] + "..." # Preview
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SmartAssistantChatView(APIView):
    """
    Agentic chat endpoint for the workplace assistant.
    Handles policy questions (RAG) and actions (Tools like leave/attendance).
    Now maintains history in Redis for a persistent experience.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_history(self, user_id):
        from langchain_community.chat_message_histories import RedisChatMessageHistory
        return RedisChatMessageHistory(
            session_id=f"chat_{user_id}",
            url=settings.REDIS_URL,
            ttl=86400  # 24 hours
        )

    def get(self, request):
        """Retrieve chat history for the current user"""
        history = self.get_history(request.user.id)
        messages = []
        for msg in history.messages:
            role = "user" if msg.type == "human" else "assistant"
            # Get timestamp from additional_kwargs if it exists
            timestamp = msg.additional_kwargs.get('timestamp')
            messages.append({
                "role": role, 
                "content": msg.content,
                "timestamp": timestamp
            })
        return Response({"history": messages})

    def post(self, request):
        query = request.data.get('query')
        if not query:
            return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from .graph import app
            from langchain_core.messages import HumanMessage, AIMessage
            from django.http import StreamingHttpResponse
            from django.utils import timezone
            import json
            import asyncio
            import threading
            import queue

            # 1. Initialize Redis History
            history_manager = self.get_history(request.user.id)
            existing_messages = history_manager.messages
            
            # 2. Add current query
            all_messages = list(existing_messages) + [HumanMessage(content=query)]
            
            # 3. Initialize State
            initial_state = {
                "messages": all_messages,
                "user_id": request.user.id,
                "organization_id": request.user.organization.id if request.user.organization else 0,
                "latitude": request.data.get('latitude', 0),
                "longitude": request.data.get('longitude', 0),
            }

            q = queue.Queue()

            def run_async_stream():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def collect_stream():
                    content_accumulated = ""
                    try:
                        async for event in app.astream_events(initial_state, version="v2"):
                            kind = event.get("event")
                            if kind == "on_chat_model_stream":
                                content = event["data"]["chunk"].content
                                if content:
                                    content_accumulated += content
                                    q.put({'token': content})
                        
                        # Save to history
                        now_iso = timezone.now().isoformat()
                        history_manager.add_message(HumanMessage(content=query, additional_kwargs={"timestamp": now_iso}))
                        history_manager.add_message(AIMessage(content=content_accumulated, additional_kwargs={"timestamp": now_iso}))
                        
                        # Send final history
                        final_history_messages = history_manager.messages
                        formatted_history = []
                        for msg in final_history_messages:
                            role = "user" if msg.type == "human" else "assistant"
                            timestamp = msg.additional_kwargs.get('timestamp')
                            formatted_history.append({
                                "role": role, 
                                "content": msg.content,
                                "timestamp": timestamp
                            })
                        q.put({'history': formatted_history})
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        q.put({'error': str(e)})
                    finally:
                        q.put(None) # Sentinel

                loop.run_until_complete(collect_stream())
                loop.close()

            def stream_generator():
                # Start the async thread
                thread = threading.Thread(target=run_async_stream)
                thread.start()

                while True:
                    item = q.get()
                    if item is None:
                        break
                    if 'error' in item:
                        yield f"data: {json.dumps(item)}\n\n"
                        break
                    yield f"data: {json.dumps(item)}\n\n"
                
                yield "data: [DONE]\n\n"

            return StreamingHttpResponse(stream_generator(), content_type='text/event-stream')

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        """Clear chat history"""
        history = self.get_history(request.user.id)
        history.clear()
        return Response({"detail": "History cleared successfully"})


