import logging

from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .models import PolicyFile, AIConfiguration
from .serializers import PolicyFileSerializer, AIConfigurationSerializer

logger = logging.getLogger(__name__)


def _normalize_llm_content(content) -> str:
    """
    Gemini (and some providers) return content as a list of parts, not a string.
    Normalize to plain text for streaming, history, and string concat.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                text = getattr(part, "text", None)
                if text:
                    parts.append(str(text))
                elif part is not None:
                    parts.append(str(part))
        return "".join(parts)
    return str(content)


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
                print(f"[OK] Proactively processed file: {instance.title}")
        except Exception as e:
            print(f"[WARN] Proactive processing failed: {str(e)}")
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
            from .retrieval import hybrid_search

            similar_docs = hybrid_search(query, organization_id)
            
            if not similar_docs:
                return Response({
                    'answer': "I couldn't find any policy documents for your organization. Please ensure policies are uploaded and processed.",
                    'sources': []
                })

            # Prepare context
            context_parts = []
            for doc in similar_docs:
                page = doc.get('page_number')
                page_note = f" (page {page})" if page else ""
                context_parts.append(f"[{doc['title']}{page_note}]\n{doc['content']}")
            context_text = "\n\n".join(context_parts)
            
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
            When you cite a policy, mention the document title and page number when available.

            FORMATTING: If you find an answer, wrap the most important part of the policy in:
            [INSIGHT_CARD] title: {Policy Name} | message: {The core policy details} | type: info | topic: Policy [/INSIGHT_CARD]
            """
            
            prompt = ChatPromptTemplate.from_template(template)
            chain = prompt | llm | StrOutputParser()
            
            answer = chain.invoke({
                "context": context_text,
                "question": query
            })
            
            # Collect sources with page citations
            sources = [
                {
                    'title': doc['title'],
                    'file_id': doc.get('file_id'),
                    'file_url': doc.get('file_url'),
                    'page_number': doc.get('page_number'),
                    'score': doc.get('score'),
                    'match_type': doc.get('match_type'),
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

# Process-local fallback when Redis is unreachable (local DEBUG / outages).
_MEMORY_CHAT_HISTORIES = {}


class SmartAssistantChatView(APIView):
    """
    Agentic chat endpoint for the workplace assistant.
    Handles policy questions (RAG) and actions (Tools like leave/attendance).
    Now maintains history in Redis for a persistent experience.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_history(self, user_id, context='user'):
        from langchain_community.chat_message_histories import (
            ChatMessageHistory,
            RedisChatMessageHistory,
        )

        # Isolate chat based on context (admin panel vs user portal)
        session_id = f"chat_{user_id}_{context}"

        # Prefer in-memory when Django is configured that way (local DEBUG).
        if getattr(settings, "USE_INMEMORY_CHANNELS", False):
            if session_id not in _MEMORY_CHAT_HISTORIES:
                _MEMORY_CHAT_HISTORIES[session_id] = ChatMessageHistory()
            return _MEMORY_CHAT_HISTORIES[session_id]

        try:
            history = RedisChatMessageHistory(
                session_id=session_id,
                url=settings.REDIS_URL,
                ttl=86400,  # 24 hours
            )
            # Probe connectivity — constructor does not always fail eagerly.
            _ = history.messages
            return history
        except Exception as e:
            logger.warning("Redis chat history unavailable (%s); using memory fallback", e)
            if session_id not in _MEMORY_CHAT_HISTORIES:
                _MEMORY_CHAT_HISTORIES[session_id] = ChatMessageHistory()
            return _MEMORY_CHAT_HISTORIES[session_id]

    def get(self, request):
        """Retrieve chat history for the current user and context"""
        try:
            context = request.query_params.get('context', 'user')
            history = self.get_history(request.user.id, context=context)
            messages = []
            for msg in history.messages:
                role = "user" if msg.type == "human" else "assistant"
                timestamp = msg.additional_kwargs.get('timestamp')
                messages.append({
                    "role": role,
                    "content": _normalize_llm_content(msg.content),
                    "timestamp": timestamp
                })

            org = getattr(request.user, "organization", None)
            config_obj = None
            if org:
                config_obj = AIConfiguration.objects.filter(
                    organization_id=org.id,
                    is_active=True
                ).first()

            config_data = {
                "model_name": config_obj.model_name if config_obj else "gpt-4o-mini",
                "temperature": config_obj.temperature if config_obj else 0.7,
            }

            return Response({
                "history": messages,
                "config": config_data
            })
        except Exception as e:
            logger.exception("Failed to load assistant history")
            return Response({
                "history": [],
                "config": {"model_name": "gpt-4o-mini", "temperature": 0.7},
                "warning": str(e),
            })

    def post(self, request):
        query = request.data.get('query')
        context = request.data.get('context', 'user') # 'admin' or 'user'
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
            import traceback

            # 1. Initialize chat history (Redis with in-memory fallback)
            try:
                history_manager = self.get_history(request.user.id, context=context)
                existing_messages = history_manager.messages
            except Exception as e:
                logger.exception("Chat history init failed")
                return Response({'error': f'History Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 2. Add current query
            all_messages = list(existing_messages) + [HumanMessage(content=query)]
            
            # 3. Initialize State
            try:
                org_id = request.user.organization.id if request.user.organization else 0
                payslip_id = request.data.get('payslip_id') or request.data.get('payload', {}).get('payslip_id')
                payslip_context = None
                
                if payslip_id:
                    from payroll.models import Payslip
                    try:
                        payslip = Payslip.objects.get(id=payslip_id, user=request.user)
                        components_str = "\n".join([f"- {c.component_name} ({c.component_type}): Rs {c.amount}" for c in payslip.components.all()])
                        payslip_context = (
                            f"Payslip for {payslip.payroll_run.month}/{payslip.payroll_run.year}\n"
                            f"Gross Earnings: Rs {payslip.gross_earnings}\n"
                            f"Total Deductions: Rs {payslip.total_deductions}\n"
                            f"Net Pay: Rs {payslip.net_pay}\n"
                            f"Worked Days: {payslip.worked_days}\n"
                            f"LOP Days: {payslip.lop_days}\n"
                            f"Components:\n{components_str}\n"
                            f"HINT: When asked to explain this payslip, use the [PAYROLL_CARD] format specified in your instructions."
                        )
                    except Payslip.DoesNotExist:
                        pass
                
                initial_state = {
                    "messages": all_messages,
                    "user_id": request.user.id,
                    "organization_id": org_id,
                    "user_role": getattr(request.user, "role", "employee"),
                    "latitude": request.data.get('latitude', 0),
                    "longitude": request.data.get('longitude', 0),
                    "payslip_context": payslip_context,
                    "page_path": request.data.get("page_path")
                    or request.data.get("payload", {}).get("page_path")
                    or "",
                    "app_context": context if context in ("admin", "user") else "user",
                }
            except Exception as e:
                print(f"[ERR] State Initialization Error: {str(e)}")
                return Response({'error': f'State Initialization Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            q = queue.Queue()

            def run_async_stream():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def collect_stream():
                    content_accumulated = ""
                    mcp_client = None
                    try:
                        from .graph import build_graph
                        # Build graph with MCP tools (or legacy fallback)
                        compiled_app, mcp_client = await build_graph(
                            organization_id=initial_state["organization_id"],
                            user_id=initial_state["user_id"],
                            user_role=initial_state.get("user_role"),
                        )

                        async for event in compiled_app.astream_events(initial_state, version="v2"):
                            kind = event.get("event", "")
                            name = event.get("name", "")
                            run_name = event.get("run_name", "")

                            # Log ALL events for debugging (will remove once confirmed working)
                            if kind not in ("on_chat_model_stream", "on_chat_model_start"):
                                logger.info(f"[StreamEvent] kind={kind} name={name!r} run_name={run_name!r}")

                            if kind == "on_chat_model_stream":
                                content = _normalize_llm_content(
                                    event["data"]["chunk"].content
                                )
                                if content:
                                    content_accumulated += content
                                    q.put({'token': content})

                            elif kind in ("on_tool_start", "on_tool_end"):
                                # Get the best available tool name from event fields
                                # LangGraph v2: individual @tool functions use name=actual_tool_name
                                # ToolNode chain uses name="tools"
                                candidate = name or run_name or ""
                                # Strip teamzen__ prefix from MCP tools
                                candidate = candidate.replace("teamzen__", "")
                                # Skip node-level names, only emit actual tool names
                                skip = {"tools", "agent", ""}
                                if candidate not in skip:
                                    if kind == "on_tool_start":
                                        logger.info(f"[Tool→START] {candidate}")
                                        q.put({'tool_start': candidate})
                                    else:
                                        logger.info(f"[Tool→END] {candidate}")
                                        q.put({'tool_end': candidate})
                                        # Emit structured citation sources for policy RAG
                                        if candidate == "search_policies":
                                            from .retrieval import parse_citations_from_tool_output
                                            tool_output = event.get("data", {}).get("output")
                                            sources = parse_citations_from_tool_output(tool_output)
                                            if sources:
                                                q.put({'sources': sources})

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
                                "content": _normalize_llm_content(msg.content),
                                "timestamp": timestamp
                            })
                        q.put({'history': formatted_history})
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        q.put({'error': str(e)})
                    finally:
                        q.put(None)  # Sentinel — mcp_client v0.2+ has no connection to close

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
        context = request.query_params.get('context', 'user')
        history = self.get_history(request.user.id, context=context)
        history.clear()
        return Response({"detail": "History cleared successfully"})
        
class AIConfigurationView(generics.RetrieveUpdateAPIView):
    """
    API endpoint to manage AI Model settings for the organization.
    Model selection is platform-controlled (superadmin only); company admins
    may still tune temperature / prompt / tokens for their org.
    """
    serializer_class = AIConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        if not user.organization:
            return None

        # Get or create default config for this organization
        config, _created = AIConfiguration.objects.get_or_create(
            organization=user.organization,
            defaults={
                'model_name': 'gpt-4o-mini',
                'temperature': 0.7,
                'max_tokens': 1024
            }
        )
        return config

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance:
            # Superadmins / users without an org: show platform default model
            platform = (
                AIConfiguration.objects.order_by("-updated_at").first()
            )
            return Response({
                'model_name': platform.model_name if platform else "gpt-4o-mini",
                'temperature': 0.7,
                'max_tokens': 1024,
                'system_prompt_override': '',
                'is_active': True,
            })
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_update(self, serializer):
        user = self.request.user
        # Model is a SaaS-provided setting — only platform superadmin may change it.
        if getattr(user, "role", None) != "superadmin":
            serializer.validated_data.pop("model_name", None)
        serializer.save()

    def update(self, request, *args, **kwargs):
        user = request.user
        if getattr(user, "role", None) not in ["superadmin", "admin", "hr"]:
            return Response({"detail": "Unauthorized"}, status=403)

        # Superadmin without an org: apply model as platform-wide SaaS default
        if getattr(user, "role", None) == "superadmin" and not user.organization_id:
            model_name = request.data.get("model_name")
            if not model_name:
                return Response(
                    {"detail": "model_name is required to set the platform AI model."},
                    status=400,
                )
            valid_ids = {c[0] for c in AIConfiguration.MODEL_CHOICES}
            if model_name not in valid_ids and model_name not in AIConfiguration.LEGACY_MODEL_MAP:
                return Response({"detail": "Invalid model_name."}, status=400)
            model_name = AIConfiguration.LEGACY_MODEL_MAP.get(model_name, model_name)

            from organizations.models import Organization
            updated = 0
            for org in Organization.objects.all():
                config, _ = AIConfiguration.objects.get_or_create(
                    organization=org,
                    defaults={
                        "model_name": model_name,
                        "temperature": 0.7,
                        "max_tokens": 1024,
                    },
                )
                if config.model_name != model_name:
                    config.model_name = model_name
                    config.save(update_fields=["model_name", "updated_at"])
                updated += 1
            return Response({
                "model_name": model_name,
                "temperature": 0.7,
                "max_tokens": 1024,
                "system_prompt_override": "",
                "is_active": True,
                "updated_organizations": updated,
            })

        instance = self.get_object()
        if not instance:
            return Response(
                {"detail": "No organization assigned; cannot update AI config."},
                status=400,
            )
        return super().update(request, *args, **kwargs)

