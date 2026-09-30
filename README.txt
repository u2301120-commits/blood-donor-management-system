BLOOD DONOR MANAGEMENT SYSTEM - RUN INSTRUCTIONS

1. Open this folder in VS Code.
2. Open Terminal in this folder.
3. Run:
   python -m pip install -r requirements.txt
4. Place the Firebase Admin SDK service-account JSON file in this folder and name it:
   serviceAccountKey.json
5. Run:
   python app.py
6. Open:
   http://127.0.0.1:5000

Firebase Web Push uses the VAPID public key in app.py. The browser token is saved to the logged-in donor record. Blood requests notify eligible and available donors with the same blood group who have a registered FCM token.

The Firebase service-account JSON must NOT be committed to GitHub.
