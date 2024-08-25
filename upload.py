import tqdm
import requests
import json
import os
import argparse
import bs4
import requests.adapters
import minify_html
import time

dummy='''<body>
    <h2>
        Placeholder file
    </h2>
    This file was automatically generated during an upload of HTML files.<br>
    This file will be removed once the upload is complete.<br>
    Do not delete this file unless you are sure that the upload has been cancelled.<br>
    Deleting this file while the upload is still ongoing may cause the upload to fail.
</body>'''

failed='''<body>
    <h2>
        Upload failed
    </h2>
    This file was automatically generated during an upload of HTML files.<br>
    If you see this file instead of what's supposed to be here, it means that the file could not be uploaded successfully.<br>
    It is safe to delete or edit this file.
</body>'''

absolute_links={}
file_ids={}
uploaded_files=0
files_to_upload=[]
total_bytes=0
max_name_length=0
failed_uploads=[]

def requestSanitize(request:requests.Response, ret_on_500=False):
    match request.status_code:
        case 200:
            return request
        case 404:
            print(f"\rContent not found. Did you input your credentials, spaceId, and parentId (if applicable) correctly?")
            exit(1)
        case 400:

            if any(['A page with this title already exists' in i['title'] for i in request.json()['errors']]):
                orqb = json.loads(request.request.body)
                if ignore_old:
                    pageid=spacepages[orqb['title']][0]
                    pagedata=session.get(linkbase+f"api/v2/pages/{pageid}")
                    return pagedata

                print(f"\nFailed to create page {orqb['title']} because one already exists with the same name.")
                exit(4)
            else:
                print(f"\nReceived HTTP 400 with unexpected errors: {'\n'.join([i["title"] for i in request.json()['errors']])}")
                exit(5)
        case 500:
            if ret_on_500:
                return
            print(f"\nReceived Internal Server Error from API.")
            exit(9)
        case _:
            print(f"\nReceived unexpected HTTP response code {request.status_code}.")
            exit(2)

def upload(filename, filecontent, spaceid, parentid):
    payload = {
        "spaceId": spaceid,
        "title": filename,
        "body": {
            "representation": "storage",
            "value": filecontent
        }
    }
    if parentid is not None:
        payload.update({"parentId":str(parentid)})
    try:
        return requestSanitize(session.post(url, data=json.dumps(payload))).json()
    except requests.exceptions.ConnectionError:
        print("\nFailed to connect to API. Did you input your URL correctly?")
        exit(3)

def getpages(id):
    getting=True
    pages = {}
    root="/wiki/api/v2/spaces"+f"/{id}/pages"
    while getting:
        try:
            data=requestSanitize(session.get(linkbase[:-6]+root)).json()
        except requests.exceptions.ConnectionError:
            print("\nFailed to connect to API. Did you input your URL correctly?")
            exit(3)
        pdt=data['results']
        for i in pdt:
            pages.update({i['title']:(i['id'], i['spaceId'], i['version']['number'])})
        if 'next' in data['_links'].keys():
            root=data['_links']['next']
        else:
            getting=False
    return pages

def update(fileid, filename, filecontent, spaceid, version):
    payload = {
        "spaceId": spaceid,
        "title": filename,
        "id": fileid,
        "status": "current",
        "version": {
            "number": version,
        },
        "body": {
            "representation": "storage",
            "value": filecontent
        }
    }
    try:
        return requestSanitize(session.put(url+f"/{fileid}", data=json.dumps(payload)), ignore_500).json()
    except requests.exceptions.ConnectionError:
        print("\nFailed to connect to API. Did you input your URL correctly?")
        exit(3)
    except AttributeError:
        return None

def fixFileLinks(content, links):
    for linksource in links:
        linktarget = linkbase[:-1] + links[linksource]
        content = content.replace(linksource.lower(), linktarget)
        content = content.replace(linksource.upper(), linktarget)

    return content

def lpad(string, length, char=' '):
    return string+char*(length-len(string))

def rpad(string, length, char=' '):
    return char*(length-len(string))+string

parser=argparse.ArgumentParser('upload', description='Program to bulk upload HTML files to confluence')
parser.add_argument('account', help='Account email to find IDs for')
parser.add_argument('token', help='API token to use')
parser.add_argument('space', help="Space ID to upload to", type=int)
parser.add_argument('source', help="File source directory")
parser.add_argument('url', help='Wiki URL root. should be something like "<name>.atlassian.net".')
parser.add_argument('-p', '--parent', help="Parent page to upload under", default=None)
parser.add_argument( '--ignore-existing', help="Treat existing files as if they were created during this upload.", action='store_true', default=False)
parser.add_argument( '--ignore-upload-errors', help="Ignore upload errors and continue uploading. Has no effect on preparation phase.", action='store_true', default=False)
parser.add_argument('-e', '--encoding', help="Encoding to use when opening files. Defaults to UTF-8.", default="utf8")  # cp1252
args=parser.parse_args()

ignore_old=args.ignore_existing
ignore_500=args.ignore_upload_errors

linkbase=("https://" if not (args.url.startswith("http://") or args.url.startswith("https://")) else '')+args.url+('' if args.url.endswith('/wiki/') else ('/' if args.url.endswith('/wiki') else ('wiki/' if args.url.endswith('/') else '/wiki/')))


url=linkbase+"api/v2/pages"

session=requests.session()

session.auth=(args.account, args.token)
session.headers={"Content-Type": "application/json"}

if not os.path.exists(args.source):
    print("\nCouldn't access source directory.")
    exit(6)

files=os.listdir(args.source)

try:
    'encoding test string'.encode(args.encoding)
except LookupError:
    print(f"\n{args.encoding} is not a valid encoding.")
    exit(7)

spacepages=getpages(args.space)

for i in files:
    if i.endswith('.html'):
        filepath=os.path.join(args.source, i)
        max_name_length=max(max_name_length, len(i))
        size=os.path.getsize(filepath)
        total_bytes+=size
        files_to_upload.append((filepath, i, size))
        try:
            file=open(filepath, encoding=args.encoding)
            for _ in range(100):
                file.read(1)
        except (UnicodeError, UnicodeDecodeError, UnicodeTranslateError):
            print(f'\nFailed to open file {i} with encoding {args.encoding}.')
            exit(8)

filecount=len(files_to_upload)
filedigits=len(str(filecount))

bar=tqdm.tqdm(total=filecount, unit='files', leave=False)

for filepath, filename, filesize in files_to_upload:
    bar.desc=f"Preparing {lpad(filename, max_name_length)}"
    bar.update(0)
    filedata=upload(os.path.splitext(filename)[0].replace('_', ' ').capitalize(), dummy, args.space, args.parent)
    absolute_links.update({filename:filedata["_links"]["webui"]})
    file_ids.update({filename:filedata['id']})
    bar.update(1)

bar.close()

bar=tqdm.tqdm(total=total_bytes, unit='b', leave=False)

for filepath, filename, filesize in files_to_upload:
    bar.desc=f"Uploading {lpad(filename, max_name_length)} ({rpad(str(uploaded_files + 1), filedigits)}/{filecount})"
    bar.update(0)
    with open(filepath, 'r', encoding=args.encoding) as f:
        content=f.read()
        content=fixFileLinks(content, absolute_links)
        content=bs4.BeautifulSoup(content, 'html.parser').prettify()
        #content=minify_html.minify(content)
        formatted_name=os.path.splitext(filename)[0].replace('_', ' ').capitalize()
        if formatted_name in spacepages.keys():
            version=spacepages[formatted_name][2]+1
        else:
            version=2
        filedata=update(file_ids[filename], formatted_name, content, args.space, version)
        if filedata is None:
            if update(file_ids[filename], formatted_name, failed, args.space, version) is None:
                failed_uploads.append((filename, False))
            else:
                failed_uploads.append((filename, True))
        else:
            uploaded_files+=1
    bar.update(filesize)

bar.close()

print(f"Uploaded {uploaded_files} files.")
if failed_uploads:
    print("Failed to upload some files:")
    for fn, sc in failed_uploads:
        print(f"{fn} {"(Also failed to upload error message.)" if not sc else ''}")