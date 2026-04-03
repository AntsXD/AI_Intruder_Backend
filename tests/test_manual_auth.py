import requests

WEB_API_KEY   = "AIzaSyBYgMbUwqKASWRgBDhIcLW2xvgIbxwjsmo"
TEST_EMAIL    = "test@test.com"
TEST_PASSWORD = "Test1234@"

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