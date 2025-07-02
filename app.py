import os
import json
import requests
import webbrowser
from flask import Flask, redirect, request, session, render_template_string
from requests_oauthlib import OAuth2Session
from openai import OpenAI

# Allow HTTP for local testing
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
app = Flask(__name__)
app.secret_key = os.urandom(24)

# === CONFIGURATION ===
CLIENT_ID = 'E34A7C75887040E8B7170BEFBC27E22E'
CLIENT_SECRET = 'udF2votW59Sef_HSXP2_I1tyXZf6Ji_FSNADE3QqH7VofagE'
REDIRECT_URI = 'http://localhost:5000/callback'
OPENAI_API_KEY = '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'

AUTH_BASE_URL = 'https://login.xero.com/identity/connect/authorize'
TOKEN_URL = 'https://identity.xero.com/connect/token'
API_BASE_URL = 'https://api.xero.com/api.xro/2.0'


# === FORMAT UTIL ===
def format_report(report, title):
    if not report or "Reports" not in report:
        return f"### {title} Report Not Available"

    rows = report["Reports"][0].get("Rows", [])
    lines = [f"### 📊 {title} Summary\n"]

    for section in rows:
        if section.get("RowType") == "Section":
            header = section.get("Title", "")
            if header:
                lines.append(f"#### {header}")
            for row in section.get("Rows", []):
                if row.get("RowType") == "Row":
                    cells = row.get("Cells", [])
                    if len(cells) >= 2:
                        label = cells[0].get("Value", "").strip()
                        value = cells[1].get("Value", "").strip()
                        if label and value:
                            lines.append(f"- **{label}**: {value}")
    return "\n".join(lines)


# === ROUTES ===
@app.route('/')
def login():
    xero = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=['accounting.reports.read'])
    auth_url, _ = xero.authorization_url(AUTH_BASE_URL)
    return redirect(auth_url)


@app.route('/callback')
def callback():
    try:
        xero = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI)
        token = xero.fetch_token(
            TOKEN_URL,
            client_secret=CLIENT_SECRET,
            authorization_response=request.url,
        )

        access_token = token['access_token']
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }

        # Get Tenant ID
        conn_resp = requests.get("https://api.xero.com/connections", headers=headers).json()
        tenant_id = conn_resp[0]["tenantId"]
        headers["Xero-tenant-id"] = tenant_id

        # Fetch reports
        pl_data = requests.get(f"{API_BASE_URL}/Reports/ProfitAndLoss", headers=headers).json()
        bs_data = requests.get(f"{API_BASE_URL}/Reports/BalanceSheet", headers=headers).json()

        # Format summaries
        pl_summary = format_report(pl_data, "Profit & Loss")
        bs_summary = format_report(bs_data, "Balance Sheet")

        # Build initial prompt context
        session['chat_history'] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful financial assistant. Use markdown formatting for responses "
                    "including headings, bullet points, and bold text. Be concise and clear."
                )
            },
            {"role": "user", "content": f"{pl_summary}\n\n{bs_summary}"}
        ]

        return redirect("/chat")

    except Exception as e:
        import traceback
        return f"<h2>❌ Internal Server Error</h2><pre>{traceback.format_exc()}</pre>"


@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'chat_history' not in session:
        return redirect("/")

    if request.method == 'POST':
        user_input = request.form['message']
        session['chat_history'].append({"role": "user", "content": user_input})

        client = OpenAI(api_key=OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=session['chat_history']
        )

        assistant_response = completion.choices[0].message.content
        session['chat_history'].append({"role": "assistant", "content": assistant_response})

    chat_html = """
    <html><head><title>Xero Chatbot</title></head>
    <body style='font-family: sans-serif; max-width: 700px; margin: auto'>
    <h2>💬 Xero Financial Chatbot</h2>
    <form method="post">
        <input name="message" placeholder="Ask about cash flow, trends, risks..." style="width: 80%" />
        <input type="submit" value="Send" />
    </form>
    <hr>
    """

    for msg in session['chat_history'][2:]:  # Skip system + initial summary
        role = "<b>🧑 You:</b>" if msg['role'] == 'user' else "<b>🤖 GPT:</b>"
        chat_html += f"<p>{role}<br><div style='white-space: pre-wrap;'>{msg['content']}</div></p>"

    chat_html += "</body></html>"
    return chat_html


if __name__ == '__main__':
    app.debug = True
    print("✅ Flask app running at http://localhost:5000")
    webbrowser.open("http://localhost:5000")
    app.run(port=5000)
