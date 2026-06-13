import requests_unixsocket
session = requests_unixsocket.Session()
res = session.get("http+unix://%2Fhome%2Flpcrm%2Flpcrmaws-backend%2Flpcrm.sock/api/branches/?company=LP")
print(res.status_code)
print(res.text)
