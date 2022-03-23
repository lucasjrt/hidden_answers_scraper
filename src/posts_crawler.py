import os
import re
import sys
import time

from queue import Queue
from threading import Event, Lock, Thread

from bs4 import BeautifulSoup
from requests.exceptions import Timeout, SSLError
from requests.exceptions import ConnectionError as ConnError

from src.tor_requests import tor_get

processing_links = Queue()
post_processing_links = Queue()
all_known_links = []

MAX_THREADS = 10
TIME_BETWEEN_REQUESTS = 1000
current_threads = 0

list_lock = Lock()
post_list = Lock()
count_lock = Lock()

thread_control = Event()
thread_control.set()

thread_throttle = Event()
thread_throttle.set()

running = True
OUTPUT_DIR = 'results'
BASE_URL = 'http://pt.answerszuvs3gg2l64e6hmnryudl5zgrmwm3vh65hzszdghblddvfiqd.onion'

def crawl():
    global current_threads
    global running

    print('Using a limit of {} threads'.format(MAX_THREADS))
    print('The interval between each request is {} milliseconds'.format(
        TIME_BETWEEN_REQUESTS))

    try:
        threads = []
        throttler = Thread(target=thread_pulse)
        throttler.start()
        for i in range(0,801):
            next_page = BASE_URL + '/questions?start=' + str(i*25)
            processing_links.put(next_page)
            print('Adding ' + str(i) + ' ' + next_page)

        while not processing_links.empty():
            list_lock.acquire()
            link = processing_links.get()
            list_lock.release()
            
            thread_throttle.wait()
            if current_threads >= MAX_THREADS:
                thread_control.clear()
            thread_control.wait()

            count_lock.acquire()
            current_threads += 1
            count_lock.release()

            thread = Thread(target=get_post, args=(link, ))
            threads.append(thread)
            thread_throttle.clear()
            thread.start()

        processing_links.join()

        while not post_processing_links.empty():
            post_list.acquire()
            link = post_processing_links.get()
            post_list.release()
            
            thread_throttle.wait()
            if current_threads >= MAX_THREADS:
                thread_control.clear()
            thread_control.wait()

            count_lock.acquire()
            current_threads += 1
            count_lock.release()

            thread = Thread(target=scrape, args=(link, ))
            threads.append(thread)
            thread_throttle.clear()
            thread.start()

        for thread in threads:
            thread.join()

        post_processing_links.join()
        running = False
        throttler.join()

    except (ConnError, Timeout) as e:
        print('Failed to connect {}'.format(e))
        return

def get_post(link):
    global current_threads
    response = tor_get(link)
    content = response.text
    
    if content:
        posts = []
        page = BeautifulSoup(content, 'html.parser')
        divs = page.find_all('div')
        for div in divs:
            try:
                if('qa-q-item-title' in div['class']):
                    posts.append(div.a['href'])
            except KeyError:
                pass
        for post_link in posts:
            path = post_link.split('../')[-1]
            post_list.acquire()
            print('Adicionado na fila: ' + str(BASE_URL + '/' + path))
            post_processing_links.put(BASE_URL + '/' + path)
            post_list.release()
    else:
        print('[WARNING] No content. Status code {}: {} response status'.format(
            link, response.status_code))
    list_lock.acquire()
    processing_links.task_done()
    list_lock.release()

    count_lock.acquire()
    current_threads -= 1
    thread_control.set()
    count_lock.release()

def scrape(link):
    global current_threads

    try:
        response = tor_get(link)

        status_code = response.status_code
        content = response.text

        if content:
            tag_list = []
            dir_name = ''
            posts = []
            page = BeautifulSoup(content, 'html.parser')
            
            tagsli = page.find_all('li', {'class' : 'qa-q-view-tag-item'})
            
            for li in tagsli:
                tag_list.append(li.a.text)

            tag_list.sort()
            if(tag_list):
                dir_name = OUTPUT_DIR + '/' + '__'.join(tag_list)
            else:
                dir_name = OUTPUT_DIR + '/untagged'

            if(not os.path.exists(dir_name)):
                os.makedirs(dir_name)
            
            with open(dir_name + '/' + link.split('/')[-1] + '.html', 'w') as f:
                f.write(content)
                
        else:
            print('[FAILED] THERE IS NO CONTENT IN: ' + link)

    except (ConnError, Timeout, SSLError) as e:
        print('[WARNING] EVERYTHING IS WRONG' + str(e))

    except Exception as e:
        print('[WARNING] {} exception {}'.format(link, e))

    post_list.acquire()
    print("Link processed: {} |  Remaining links: {}  | Threads: {}/{}".format(link, post_processing_links.qsize(), current_threads, MAX_THREADS))
    post_processing_links.task_done()
    post_list.release()

    count_lock.acquire()
    current_threads -= 1
    thread_control.set()
    count_lock.release()

def thread_pulse():
    global running
    interval = TIME_BETWEEN_REQUESTS / 1000
    while running:
        thread_throttle.set()
        time.sleep(interval)
