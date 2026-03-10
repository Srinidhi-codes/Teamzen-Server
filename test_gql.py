import urllib.request
import json
import os

url_login = 'https://teamzen-server.onrender.com/api/auth/login/'
data_login = {'email': 'arjun@gmail.com', 'password': 'Arjun@123'}
req_login = urllib.request.Request(url_login, data=json.dumps(data_login).encode('utf-8'))
req_login.add_header('Content-Type', 'application/json')
try:
    response = urllib.request.urlopen(req_login)
    resp_data = json.loads(response.read().decode())
    token = resp_data.get('access_token')

    url_gql = 'https://teamzen-server.onrender.com/graphql/'
    mutation = """
    mutation {
      leaveRequestProcess(input: { requestId: "10", status: REJECTED }) {
        id
        status
      }
    }
    """
    req_gql = urllib.request.Request(url_gql, data=json.dumps({'query': mutation}).encode('utf-8'))
    req_gql.add_header('Content-Type', 'application/json')
    req_gql.add_header('Authorization', f'Bearer {token}')

    gql_resp = urllib.request.urlopen(req_gql)
    print('GQL SUCCESS:', gql_resp.read().decode())
except Exception as e:
    print('Failed:', e)
