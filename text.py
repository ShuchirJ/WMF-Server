from flask import Flask, request
import pytextnow
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
tn = pytextnow.Client("coolcodersj0", sid_cookie=os.environ['TEXTNOW_SID'], csrf_cookie=os.environ['TEXTNOW_CSRF'])

@app.post('/text/<number>')
def send(number):
    tn.send_sms(number, request.json['message'])
    return "done"

app.run(host='0.0.0.0', port=2340)