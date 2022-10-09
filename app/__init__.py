import audioop
from flask import Flask, request, Response
from email.mime.multipart import MIMEMultipart
from email.message import Message
import json
from speex import SpeexDecoder
from vosk import Model, KaldiRecognizer

app = Flask(__name__)

decoder = SpeexDecoder(1)
model = Model(lang="it")
rec = KaldiRecognizer(model, 16000)
rec.SetWords(True)
rec.SetPartialWords(True)


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
        # Dirty way to remove initial/final button click
        if len(chunks) > 15:
            chunks = chunks[12:-3]

        # Transcribing audio chunk
        for chunk in chunks:
            out = decoder.decode(chunk)
            # Boosting the audio volume
            out = audioop.mul(out, 2, 4)
            rec.AcceptWaveform(out)

        final = json.loads(rec.Result())

        if final["text"]:
            output = []
            for partial in final["result"]:
                output.append({'word': partial["word"], 'confidence': str(partial["conf"])})
            output[0]['word'] += '\\*no-space-before'
            output[0]['word'] = output[0]['word'][0].upper() + output[0]['word'][1:]
            response_part.add_header('Content-Disposition', 'form-data; name="QueryResult"')
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
        print(str(e))
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

    # Resetting Recognizer
    rec.Reset()
    return response
