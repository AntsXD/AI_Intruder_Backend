import requests
from app.config import settings

WEB_API_KEY = settings.firebase_web_api_key
TEST_EMAIL    = "christy.n.chamoun@gmail.com"
TEST_PASSWORD = "TestTest123@!"

response = requests.post(
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}",
    json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "returnSecureToken": True
    }
)

print(response.status_code)
print(response.json())