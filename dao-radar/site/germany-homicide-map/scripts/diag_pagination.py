import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlparse
u="https://www.presseportal.de/blaulicht/st/T%C3%B6tungsdelikt"
r=requests.get(u,timeout=30,headers={"User-Agent":"Mozilla/5.0"});r.raise_for_status()
s=BeautifulSoup(r.text,"html.parser")
for a in s.find_all("a",href=True):
    label=" ".join(a.get_text(" ",strip=True).split())
    if label in {"1","2","3","4","5","6","7","8","9","10"} or "Nächste" in label or "Weiter" in label:
        print(repr(label), urljoin(u,a["href"]))
