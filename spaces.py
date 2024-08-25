import requests
import argparse

parser=argparse.ArgumentParser('spaces', description='Find confluence space IDs')
parser.add_argument('account', help='Account email to find IDs for')
parser.add_argument('token', help='API token to use')
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
            print(f"Content not found. Did you input your credentials correctly?")
            exit(1)
        case _:
            print(f"Received unexpected HTTP response code {request.status_code}.")
            exit(2)

def getspaces():
    spaces = {}
    getting=True
    root="/wiki/api/v2/spaces"
    while getting:
        try:
            data=requestSanitize(session.get(url+root)).json()
        except requests.exceptions.ConnectionError:
            print("Failed to connect to API. Did you input your URL correctly?")
            exit(3)
        pdt=data['results']
        for i in pdt:
            spaces.update({i['name']:i['id']})
        if 'next' in data['_links'].keys():
            root=data['_links']['next']
        else:
            getting=False
    return spaces

spaces=getspaces()

print("Account spaces:")

for i in spaces:
    print(f"{spaces[i]}: {i}")