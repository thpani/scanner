#!/usr/bin/env python3

import errno
import os
from threading import Thread
from queue import Queue
import sqlite3
import json
import re
import sys

import requests
from bs4 import BeautifulSoup
from pushbullet import Pushbullet

from wunderlist import Wunderlist

### CONFIGURATION ###

with open('/etc/scanner.json') as f:
    j = json.load(f)
    PUSHBULLET_ACCESS_KEY = j['pushbullet']['access_key']
    PUSHBULLET_SEND_TO_CHATS = j['pushbullet']['send_to_chats']
    WUNDERLIST_ACCESS_TOKEN = {
        'X-Access-Token': j['wunderlist']['access_token'],
        'X-Client-ID': j['wunderlist']['clientid']
    }
    WUNDERLIST_LIST_ID = j['wunderlist']['default_list']
    BARCODE_SCANNER_ENV = j['scanner']['dev']
MAP = {}
DB_FILE = '/var/db/scanner/scanner.db'
USE_EVENT_DEV = False

###

class Messenger:
    def __init__(self):
        self.pb = Pushbullet(PUSHBULLET_ACCESS_KEY)
        self.chats = [ chat for chat in self.pb.chats if chat.name in PUSHBULLET_SEND_TO_CHATS ]

    def send(self, title, body):
        for chat in self.chats:
            push = chat.push_note(title, body)
            ts = push['modified']

def lookup_ean(ean):
    r = requests.get('http://www.codecheck.info/product.search', params={'q':ean, 'OK': 'Suchen'})
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, 'html.parser')
        productcreateform = soup.find(id='productcreateform')
        page = soup.find(class_='page')
        if not productcreateform:
            # the product exists
            if 'product-info' in page['class']:
                # single product page
                productname = page.find('h1').get_text().strip()
                return productname
            else:
                title = soup.find(class_='title')
                productname = title.find('h1').get_text().strip()
                return productname

class Unbuffered:
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)

class Reader(Thread):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def run(self):
        if USE_EVENT_DEV:
            import evdev
            dev = evdev.InputDevice(BARCODE_SCANNER_ENV)
            list = []

        while True:
            if USE_EVENT_DEV:
                try:
                    for event in dev.read_loop():
                        if event.type == evdev.ecodes.EV_KEY:
                            x = evdev.categorize(event)
                            if x.keystate == 0:
                                char = x.keycode[4:]
                                if char == 'ENTER':
                                    r = ''.join(list)
                                    print('input={}'.format(r))
                                    self.queue.put(r)
                                    list = []
                                else:
                                    list.append(char)
                except OSError as exc:
                    if exc.errno == 19:
                        print("[Errno 19] No such device", file=sys.stderr)
                        import time
                        time.sleep(60) # 1 min
                    else:
                        raise exc

            else:
                r = input()
                self.queue.put(r)

def lookup_db(conn, ean):
    c = conn.cursor()
    c.execute('SELECT name, list, shelf FROM products WHERE ean=?', (ean,))
    row = c.fetchone()
    return row

def add_db(conn, ean, product, listid):
    c = conn.cursor()
    c.execute('INSERT INTO products (ean, name, list) VALUES (?, ?, ?)', (ean, product, listid))
    conn.commit()

def init_db():
    mkdir_p(os.path.dirname(DB_FILE))
    db = sqlite3.connect(DB_FILE)
    spath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'schema.sql')
    with open(spath, mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()
    return db

# http://stackoverflow.com/a/600612/1161037
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def main():
    global USE_EVENT_DEV
    if len(sys.argv) > 1 and sys.argv[1] == '--evdev':
        USE_EVENT_DEV = True

        sys.stdout = Unbuffered(sys.stdout)
        sys.stderr = Unbuffered(sys.stderr)

    print("Starting up...", file=sys.stderr)

    m = Messenger()
    w = Wunderlist(WUNDERLIST_ACCESS_TOKEN)

    q = Queue()
    r = Reader(q)
    r.start()

    db = init_db()

    print("Ready.", file=sys.stderr)

    while True:
        ean = q.get()

        if ean == '99900007':
            succ, json_response = w.sort_list(WUNDERLIST_LIST_ID)
            if succ:
                print('List sort ✔', file=sys.stderr)
            else:
                print('List sort ✘', file=sys.stderr)
                print(' ', json_response, file=sys.stderr)
            continue

        product = lookup_db(db, ean)

        # if not in DB, lookup
        if product is None:
            product_name, listid = lookup_ean(ean), WUNDERLIST_LIST_ID
            if product_name is None:
                print('Lookup ✘', 'Failed to lookup EAN', ean, file=sys.stderr)
                m.send('Failed to lookup EAN', ean + '; Can you please edit it in my database?')
                product_name, listid, shelf = '??? EAN: {}'.format(ean), WUNDERLIST_LIST_ID, None
                add_db(db, ean, product_name, listid)
            else:
                print('Lookup ✔ (from codecheck.info)', product_name, file=sys.stderr)
                add_db(db, ean, product_name, listid)
                shelf = None
        else:
            product_name, listid, shelf = product
            print('Lookup ✔ (from DB)', product_name, file=sys.stderr)

        task_created, json_response = w.add_product(ean, product_name, listid, shelf)
        if task_created:
            print('Task add ✔', product_name, file=sys.stderr)
        else:
            print('Task add ✘', product_name, file=sys.stderr)
            print(' ', json_response, file=sys.stderr)
            m.send('Failed to save to Wunderlist', product_name + '\n' + json.dumps(json_response))

if __name__ == '__main__':
    main()
