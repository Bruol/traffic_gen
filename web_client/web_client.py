import requests
from bs4 import BeautifulSoup
import argparse
import time
import sys

def get_all_links(url):
    # Send a GET request to the URL
    response = requests.get(url)
    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to retrieve the webpage. Status code: {response.status_code}")
        return []

    # Parse the webpage content
    soup = BeautifulSoup(response.content, 'html.parser')
    # Find all <a> tags (which define hyperlinks)
    links = soup.find_all('a')
    # Extract the href attribute from each <a> tag
    hrefs = [link.get('href') for link in links if link.get('href')]

    links = [url+"/"+link for link in hrefs]

    return links


def main(url, duration, wait_time):


    # Get all links from the webpage
    links = get_all_links(url)
    if not links:
        print("No valid links found.")
        return
    
    start_time = time.time()

    print(f"Starting web client at {start_time} seconds.")

    i = 0
    
    while (time.time() - start_time) < duration:
        link = links[i % len(links)]
        print(f"Requesting {link} at {time.time() - start_time} seconds.", end=" -- ")
        response = requests.get(link)
        print(f"Status code: {response.status_code}", end=" -- ")
        i += 1
        print(f"Waiting for {wait_time} seconds.")
        time.sleep(wait_time)

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Web Client')

    parser.add_argument('--url', type=str, help='URL')
    parser.add_argument('--duration', type=int, help='duration')
    parser.add_argument('--wait_time', type=float, default=0, help='wait time')
    parser.add_argument('--logfile', type=str, default="", help='log file')

    args = parser.parse_args()
    if args.logfile: 
        with open(args.logfile, 'w') as f:
            sys.stdout = f

            main(args.url, args.duration, wait_time=args.wait_time)
    else:
        main(args.url, args.duration, wait_time=args.wait_time)