# Pebble Offline Dictation Service

This is a replacement dictation service based on Vosk Offline Speech To Text library.
It works fine on a Raspberry Pi 4, though there are some limitation (see install).

## How to install

This software relies on [Speex Python Library](https://pypi.org/project/speex/) which is unfortunately outdated and
works only with <=Python 3.7.

Before proceeding, if it's not already, you need to install Python 3.7 as an alternative of the version currently
installed on your system. I won't cover this part, there are already plenty of tutorials on internet on how to do this.

Steps to install the app:
* Clone the project and enter the folder:
```shell
git clone https://github.com/nico9889/pebble-ds.git
cd pebble-ds
```
* Create a virtual environment: 
```shell
python3.7 -m venv venv
```
* Activate the virtual environment:
```shell
source venv/bin/activate
```
* Install the Debian/Ubuntu requirements to compile speex:

```shell
sudo apt-get install build-essential libspeex-dev libspeexdsp-dev libpulse-dev
```

* Install the required Python modules:
```shell
pip install -r requirements.txt
```

**Note:** Gunicorn may fail to install because of a bug. A patch exists and has been merged on the Gunicorn repository
but it's still not released.

Workaround:
```shell
pip uninstall gunicorn
pip install https://github.com/benoitc/gunicorn/archive/refs/heads/master.zip --no-cache-dir
```

* Change the Vosk model language in `app/__init__.py`:
```Python3
# https://github.com/nico9889/pebble-ds/blob/efe33d4d0827ba04e91e8d1ef0197de645527aca/app/__init__.py#L12
model = Model(lang="YOUR_LANGUAGE_HERE")
```

You can obtain a list of supported languages by issuing the command:
```shell
vosk-transcriber --list-languages
```

* Start the application:
```shell
python app.py
```

To use the application you need to apply a Reverse Proxy (I.E: Nginx) in front of the app to upgrade the connection
from HTTP to HTTPS, a self-signed certificate should be enough.
As an alternative you can use Cloudflare Tunnel service (though it may be not the best solution if privacy is a major
concern to you).

Steps on Rebble Website:

* Login on https://rebble.io
* Click on "My Account"
* Click on the button on the bottom "I know what I'm doing, show me the options anyway!"
* Change the configuration in:

```json
{
    "config": {
        "voice": {
            "languages": [
                {
                    "endpoint": "YOUR_HOSTNAME_HERE",
                    "six_char_locale": "ita_ITA",
                    "four_char_locale": "it_IT"
                }
            ],
            "first_party_uuids": [
                ""
            ]
        }
    }
}
```

`six_char_locale` and `four_char_locale` should be changed accordingly to the corresponding of your language.

**Warning:** if you write an invalid `six_char_locale` or `four_char_locale` the configuration will be still accepted
but won't work while configuring the Pebble App on your phone.
**It fails silently**, no error is showing up, I learnt that the hard way by using "-" instead of "_".

* Click on "Ok, well, I guess that looks good."
* Open "https://boot.rebble.io" on your phone and do the configuration again

If everything has been done correctly, in the Pebble App settings, Dictation section, you should see
only the languages that you configured as available. **Be sure to select a language to override the default settings**.

## Start as a service
The following steps has been tested only on Raspberry Pi and MAY work on Debian/Ubuntu:
* Create a new service with your favourite editor (I use Nano, at least I know how to close it):
```shell
sudo nano /etc/systemd/system/pebble-ds.conf
```
* Copy the following configuration, changing the PATH_TO_PEBBLE_DS to the corresponding on your system:
```shell
[Unit]
Description=Pebble Vosk Based Dictation service
After=network.target

[Service]
User=pi
Group=www-data
WorkingDirectory=/PATH_TO_PEBBLE_DS/pebble-ds/
Environment="PATH=/PATH_TO_PEBBLE_DS/pebble-ds/venv/bin"
ExecStart=/PATH_TO_PEBBLE_DS/pebble-ds/venv/bin/gunicorn --access-logfile - --workers 1 --bind 127.0.0.1:9001 --worker-class eventlet app:app

[Install]
WantedBy=multi-user.target
```
* Enable the service automatic restart/start at boot:
```shell
sudo systemctl enable pebble-ds.service
```
* Start the service
```shell
sudo systemctl start pebble-ds.service
```

## Resources:
* Vosk: https://github.com/alphacep/vosk-api
* Rebble ASR: https://github.com/pebble-dev/rebble-asr
* Reddit discussion for Rebble Service configuration: https://www.reddit.com/r/pebble/comments/llqdv6/self_hosted_dictation_service/

## TODO:
* Change the app, so it takes advantage of the per-language URL to determine the model.
* Punctuation (maybe with a replacement dictionary initially)
* Docker configuration(?)


