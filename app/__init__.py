from flask import Flask, request, Response
from email.mime.multipart import MIMEMultipart
from email.message import Message
import json
from speex import SpeexDecoder
from rnnoise_wrapper import RNNoise
from pydub import AudioSegment
import random
import audioop
import io

app = Flask(__name__)

decoder = SpeexDecoder(1)

sbertoken = ''
tokenexp = 0

try:
    rnnoise = RNNoise("/usr/local/lib/librnnoise.so")
except Exception as e:
    rnnoise = None
    print("RNNoise not found")

@app.route("/heartbeat")
def heartbeat():
    return "asr"

# From: https://github.com/pebble-dev/rebble-asr/blob/37302ebed464b7354accc9f4b6aa22736e12b266/asr/__init__.py#L27
def parse_chunks(stream):
    boundary = b'--' + request.headers['content-type'].split(';')[1].split('=')[1].encode(
        'utf-8').strip()  # super lazy/brittle parsing.
    this_frame = b''
    while True:
        content = stream.read(4096)
        this_frame += content
        end = this_frame.find(boundary)
        if end > -1:
            frame = this_frame[:end]
            this_frame = this_frame[end + len(boundary):]
            if frame != b'':
                try:
                    header, content = frame.split(b'\r\n\r\n', 1)
                except ValueError:
                    continue
                yield content[:-2]
        if content == b'':
            break

def salutespeech_updatetoken():
    import requests
    from config import settings
    
    secret_auth = settings['secret_auth']
    rquid = settings['rquid']

    url = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
    headers = {
        'Authorization': 'Basic '+secret_auth,
        'RqUID': rquid,
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    response = requests.post(url, headers=headers, data="scope=SALUTE_SPEECH_PERS", verify=False)

    global sbertoken
    global tokenexp
    sbertoken = json.loads(response.text)["access_token"]
    tokenexp = (float(json.loads(response.text)["expires_at"]) / 1000) - 60*5

def salutespeech_recognize(binary): # wtffff quok reference
    import requests
    import time
    # check if token is expired
    current_unix_time = int(time.time())
    if tokenexp < current_unix_time:
        salutespeech_updatetoken()

    url = 'https://smartspeech.sber.ru/rest/v1/speech:recognize'
    headers = {
        'Authorization': 'Bearer '+sbertoken,
        'Content-Type': 'audio/x-pcm;bit=16;rate=16000'
    }

    response = requests.post(url, headers=headers, data=binary, verify=False)

    words = ''
    wordstmp = json.loads(response.text)["result"];
    for sentence in wordstmp:
        words += sentence

    return words


@app.post("/NmspServlet/")
def asr():
    stream = request.stream

    # Parsing request
    chunks = list(parse_chunks(stream))[3:]  # 0 = Content Type, 1 = Header?

    # Preparing response
    # From: https://github.com/pebble-dev/rebble-asr/blob/37302ebed464b7354accc9f4b6aa22736e12b266/asr/__init__.py#L92
    # Now for some reason we also need to give back a mime/multipart message...
    parts = MIMEMultipart()
    response_part = Message()
    response_part.add_header('Content-Type', 'application/JSON; charset=utf-8')

    try:
        complete = AudioSegment.empty()

        # Dirty way to remove initial/final button click
        if len(chunks) > 15:
            chunks = chunks[12:-3]
        for chunk in chunks:
            decoded = decoder.decode(chunk)
            # Boosting the audio volume
            # decoded = audioop.mul(decoded, 2, 6)
            audio = AudioSegment(decoded, sample_width=2, frame_rate=16000, channels=1)
            if rnnoise:
                audio = rnnoise.filter(audio[0:10]) + rnnoise.filter(audio[10:20])
            complete += audio

        ### For debugging purposes. Uncomment this if you wanna hear what's coming from Pebble's microphone
        # filename = str(random.random()) + ".wav"
        # complete.export(out_f=filename, format="wav")

        buffer = io.BytesIO()
        complete.export(buffer, format="wav")
        final = salutespeech_recognize(buffer)

        if final:
            response_part.add_header('Content-Disposition', 'form-data; name="QueryResult"')
            output = []
            for word in final.split(" "):
                output.append({'word': word, 'confidence': 1})
            output[0]['word'] += '\\*no-space-before'
            response_part.set_payload(json.dumps({
                'words': [output],
            }))
        else:
            print("No words detected")
            response_part.add_header('Content-Disposition', 'form-data; name="QueryRetry"')
            response_part.set_payload(json.dumps({
                "Cause": 1,
                "Name": "AUDIO_INFO",
                "Prompt": "Sorry, speech not recognized. Please try again."
            }))
    except Exception as e:
        print("Error occurred:", str(e))
        response_part.add_header('Content-Disposition', 'form-data; name="QueryRetry"')
        response_part.set_payload(json.dumps({
            "Cause": 1,
            "Name": "AUDIO_INFO",
            "Prompt": "Error while decoding incoming audio."
        }))

    # Closing response
    # From: https://github.com/pebble-dev/rebble-asr/blob/37302ebed464b7354accc9f4b6aa22736e12b266/asr/__init__.py#L113
    parts.attach(response_part)
    parts.set_boundary('--Nuance_NMSP_vutc5w1XobDdefsYG3wq')
    response = Response('\r\n' + parts.as_string().split("\n", 3)[3].replace('\n', '\r\n'))
    response.headers['Content-Type'] = f'multipart/form-data; boundary={parts.get_boundary()}'

    return response
