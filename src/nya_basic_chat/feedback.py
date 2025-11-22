import requests
import base64
from nya_basic_chat.config import get_secret


def send_graph_email(subject, body, attachments=None):
    # Get access token

    token_url = (
        f"https://login.microsoftonline.com/{get_secret('AZURE_TENANT_ID')}/oauth2/v2.0/token"
    )
    token_data = {
        "client_id": get_secret("AZURE_APP_CLIENT_ID"),
        "client_secret": get_secret("AZURE_CLIENT_SECRET"),
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    # print("DEBUG: token_url =", token_url)
    # print("DEBUG: token request payload =", token_data)
    token_res = requests.post(token_url, data=token_data)
    # print("DEBUG: token status =", token_res.status_code)
    # print("DEBUG: token response =", token_res.text)
    access_token = token_res.json()["access_token"]

    # Build message
    graph_attachments = []
    for f in attachments or []:
        content = base64.b64encode(f.read()).decode("utf-8")
        graph_attachments.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": f.name,
                "contentBytes": content,
            }
        )

    email_data = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": get_secret("GRAPH_SEND_TO")}}],
            "attachments": graph_attachments,
        },
        "saveToSentItems": "true",
    }

    # Send mail
    send_url = f"https://graph.microsoft.com/v1.0/users/{get_secret('GRAPH_FROM')}/sendMail"
    headers = {"Authorization": f"Bearer {access_token}"}

    # print("DEBUG: send_url =", send_url)
    # print("DEBUG: send request payload =", email_data)
    send_res = requests.post(send_url, json=email_data, headers=headers)
    # print("DEBUG: send status =", send_res.status_code)
    # print("DEBUG: send response =", send_res.text)
    return send_res
