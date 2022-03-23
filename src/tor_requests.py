import os
import sys

import requests

from fake_useragent import UserAgent
from requests.exceptions import ConnectionError as ConnError
from stem import Signal
from stem.control import Controller

TIMEOUT = 300
MAX_RETRIES = 10

try:
    TOR_PASS = os.environ['TOR_PASS']
except KeyError:
    print('Expected TOR_PASS environment variable')
    sys.exit(2)

tor_proxy = {
    "http": "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050"
}

headers = {
    "User-Agent": UserAgent().random
}


def new_tor_id():
    with Controller.from_port(port=9051) as controller:
        controller.authenticate(password=TOR_PASS)
        controller.signal(Signal.NEWNYM)


def tor_get(url: str):
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            new_tor_id()
            response = requests.get(url, headers=headers,
                                    proxies=tor_proxy, timeout=TIMEOUT)
            if attempt:
                print('{} succeeded after {} attempts!'.format(url, attempt))
            return response
        except ConnError as e:
            try:
                try:
                    code, message = e.__context__.__context__.__context__.socket_err.msg.split(': ')
                    if code == '0x04':
                        print('[WARNING] Host unreachable, not retrying to connect')
                        raise ConnError(message)
                    elif code == '0x06':
                        attempt += 1
                        if attempt >= MAX_RETRIES:
                            print('[WARNING] {} reached max attempts.'.format(url))
                            raise ConnError(message)
                        print('[WARNING] {} failed on attempt {}, trying again. ({})'.format(url, attempt, str(e)))
                    else:
                        raise e
                except AttributeError as e1:
                    raise e
            except ConnError as e:
                print('[WARNING] Exception: {}'.format(e))
                raise e
        except Exception as e:
            print('[WARNING] Unexpected generic exception')
            raise e
