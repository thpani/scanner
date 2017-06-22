import re

import requests

class RequestFailedException(Exception):
    def __init__(self, message, json):
        self.message = message
        self.json = json

class Wunderlist:
    api_url = 'https://a.wunderlist.com/api/v1'

    def __init__(self, access_token):
        self.headers = access_token

    class Product:
        def __init__(self, name, count, task):
            self.name, self.count, self.task = name, count, task

    def add_task(self, ean, text, listid, shelf):
        r = requests.post(
            Wunderlist.api_url+'/tasks',
            headers=self.headers,
            json={ 'list_id': listid, 'title': text }
        )
        if r.status_code != 201:
            return r.status_code == 201, r.json()

        r_comment = requests.post(
            Wunderlist.api_url+'/task_comments',
            headers=self.headers,
            json={ 'task_id': r.json()['id'], 'text': 'EAN: {}, Shelf: {}'.format(ean, shelf) }
        )

        return r_comment.status_code == 201, r_comment.json()

    def modify_task(self, id, text, revision):
        r = requests.patch(
            Wunderlist.api_url+'/tasks/{}'.format(id),
            headers=self.headers,
            json={ 'revision': revision, 'title': text }
        )
        return r.status_code == 200, r.json()
    
    def get_products(self, listid):
        r = requests.get(
            Wunderlist.api_url+'/tasks',
            headers=self.headers,
            params={ 'list_id': listid }
        )
        if r.status_code != 200:
            raise RequestFailedException('GET products (list {}) failed: {}'.format(listid, r.status_code), r.json())

        products = []
        for task in r.json():
            match = re.match('((\d+)x )?(.*)', task['title'])

            name = match.group(3)
            count = int(match.group(2)) if match.group(2) else 1

            product = Wunderlist.Product(name, count, task)
            products.append(product)
        
        return products

    def add_product(self, ean, product_name, listid, shelf):
        products = self.get_products(listid)
        plist = [ p for p in products if p.name == product_name ]  # tasks that contain `product`
        if not plist:
            return self.add_task(ean, product_name, listid, shelf)
        else:
            p = plist[0]
            return self.modify_task(
                p.task['id'],
                '{}x {}'.format(p.count+1, product_name),
                p.task['revision']
            )
    
    def sort_list(self, listid):
        r = requests.get(
            Wunderlist.api_url+'/task_comments',
            headers=self.headers,
            params={ 'list_id': listid }
        )
        if r.status_code != 200:
            raise RequestFailedException('GET list comments (list {}) failed: {}'.format(listid, r.status_code), r.json())

        comments = [ comment for comment in r.json() if 'Shelf: ' in comment['text'] ]
        comments = sorted(comments, key=lambda comment: re.search('Shelf: (.*)', comment['text']).group(1))
        task_ids = [ comment['task_id'] for comment in comments ]

        if not task_ids:
            return True, {}

        r = requests.get(
            Wunderlist.api_url+'/task_positions',
            headers=self.headers,
            params={ 'list_id': listid }
        )
        if r.status_code != 200:
            raise RequestFailedException('GET list positions (list {}) failed: {} {}'.format(listid, r.status_code), r.json())

        assert(len(r.json()) == 1)
        revision = r.json()[0]['revision']

        r = requests.patch(
            Wunderlist.api_url+'/task_positions/{}'.format(listid),
            headers=self.headers,
            json={ 'revision': revision, 'values': task_ids }
        )
        return r.status_code == 200, r.json()
