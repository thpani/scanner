#!/usr/bin/env python3

from threading import Thread
from queue import Queue
import sqlite3
import json
import re
import sys

import requests
from bs4 import BeautifulSoup
from pushbullet import Pushbullet

### CONFIGURATION ###

with open('config.json') as f:
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
DB_FILE = 'scanner.db'
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

class Wunderlist:
    headers = WUNDERLIST_ACCESS_TOKEN
    api_url = 'https://a.wunderlist.com/api/v1'

    class Product:
        def __init__(self, name, count, task):
            self.name, self.count, self.task = name, count, task

    def add_task(self, text, listid):
        r = requests.post(
            Wunderlist.api_url+'/tasks',
            headers=Wunderlist.headers,
            json={ 'list_id': listid, 'title': text }
        )
        return r.status_code == 201, r.json()

    def modify_task(self, id, text, revision):
        r = requests.patch(
            Wunderlist.api_url+'/tasks/{}'.format(id),
            headers=Wunderlist.headers,
            json={ 'revision': revision, 'title': text }
        )
        return r.status_code == 200, r.json()
    
    def get_products(self, listid):
        r = requests.get(
            Wunderlist.api_url+'/tasks',
            headers=Wunderlist.headers,
            params={ 'list_id': listid }
        )
        if r.status_code != 200:
            raise # TODO

        products = []
        for task in r.json():
            match = re.match('((\d+)x )?(.*)', task['title'])

            name = match.group(3)
            count = int(match.group(2)) if match.group(2) else 1

            product = Wunderlist.Product(name, count, task)
            products.append(product)
        
        return products

    def add_product(self, product_name, listid):
        products = self.get_products(listid)
        plist = [ p for p in products if p.name == product_name ]  # tasks that contain `product`
        if not plist:
            return self.add_task(product_name, listid)
        else:
            p = plist[0]
            return self.modify_task(
                p.task['id'],
                '{}x {}'.format(p.count+1, product_name),
                p.task['revision']
            )

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
        while True:
            r = self.readline()
            self.queue.put(r)
    def readline(self):
        if USE_EVENT_DEV:
            dev = evdev.InputDevice(BARCODE_SCANNER_ENV)
    
            list = []
            for event in dev.read_loop():
                if event.type == evdev.ecodes.EV_KEY:
                     x = evdev.categorize(event)
                     if x.keystate == 0:
                         char = x.keycode[4:]
                         if char == 'ENTER':
                             result = ''.join(list)
                             print('input={}'.format(result))
                             return result
                         else:
                             list.append(char)
        else:
            return input()

def lookup_db(conn, ean):
    # sqlite> CREATE TABLE products (ean TEXT PRIMARY KEY, name TEXT, list INTEGER, FOREIGN KEY(list) REFERENCES lists (id));
    # sqlite> CREATE TABLE lists (id INTEGER PRIMARY KEY);
    c = conn.cursor()
    c.execute('SELECT name, list FROM products WHERE ean=?', (ean,))
    row = c.fetchone()
    return row

def add_db(conn, ean, product, listid):
    c = conn.cursor()
    c.execute('INSERT INTO products (ean, name, list) VALUES (?, ?, ?)', (ean, product, listid))
    conn.commit()

def main():
    global USE_EVENT_DEV
    if len(sys.argv) > 1 and sys.argv[1] == '-d':
        import evdev

        USE_EVENT_DEV = True

        sys.stdout = Unbuffered(sys.stdout)
        sys.stderr = Unbuffered(sys.stderr)

    print("Starting up...", file=sys.stderr)

    m = Messenger()
    w = Wunderlist()

    q = Queue()
    r = Reader(q)
    r.start()

    db_conn = sqlite3.connect(DB_FILE)

    print("Ready.", file=sys.stderr)

    while True:
        ean = q.get()
        product = lookup_db(db_conn, ean)

        # if not in DB, lookup
        if product is None:
            product_name, listid = lookup_ean(ean), WUNDERLIST_LIST_ID
            if product_name is None:
                print('Lookup ✘', 'Failed to lookup EAN', ean, file=sys.stderr)
                m.send('Failed to lookup EAN', ean + '; Can you tell me what it is?')
                continue
            else:
                print('Lookup ✔ (from codecheck.info)', product_name, file=sys.stderr)
                add_db(db_conn, ean, product_name, listid)
        else:
            product_name, listid = product
            print('Lookup ✔ (from DB)', product_name, file=sys.stderr)

        task_created, json_response = w.add_product(product_name, listid)
        if task_created:
            print('Task add ✔', product_name, file=sys.stderr)
        else:
            print('Task add ✘', product_name, file=sys.stderr)
            print(' ', json_response, file=sys.stderr)
            m.send('Failed to save to Wunderlist', product_name + '\n' + json.dumps(json_response))

if __name__ == '__main__':
    main()
