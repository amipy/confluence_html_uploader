import requests
import argparse

parser=argparse.ArgumentParser('spaces', description='Find confluence page IDs')
parser.add_argument('account', help='Account email to find IDs for')
parser.add_argument('token', help='API token to use')
parser.add_argument("spaceid", help="ID of the space to list", type=int)
parser.add_argument('url', help='Atlassian domain. should be something like "<name>.atlassian.net".')
args=parser.parse_args()

url=("https://" if not (args.url.startswith("http://") or args.url.startswith("https://")) else '')+args.url

session=requests.session()
session.auth=(args.account, args.token)
session.headers={"Content-Type": "application/json"}

def requestSanitize(request:requests.Response):
    match request.status_code:
        case 200:
            return request
        case 404:
            print(f"Content not found. Did you input your credentials and spaceId correctly?")
            exit(1)
        case _:
            print(f"Received unexpected HTTP response code {request.status_code}.")
            exit(2)

def getpages(id):
    getting=True
    pages = {}
    root="/wiki/api/v2/spaces"+f"/{id}/pages"
    while getting:
        try:
            data=requestSanitize(session.get(url+root)).json()
        except requests.exceptions.ConnectionError:
            print("Failed to connect to API. Did you input your URL correctly?")
            exit(3)
        pdt=data['results']
        for i in pdt:
            pages.update({i['title']:(i['id'], i['spaceId'])})
        if 'next' in data['_links'].keys():
            root=data['_links']['next']
        else:
            getting=False
    return pages

pages=getpages(args.spaceid)

print("Space pages:")

for i in pages:
    print(f"{pages[i][0]}: {i} {f'(Use spaceId {pages[i][1]} if you want this to be the parent of a file)' if args.spaceid!=int(pages[i][1]) else ''}")