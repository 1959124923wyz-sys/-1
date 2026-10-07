import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
u="https://www.presseportal.de/blaulicht/st/Raub%C3%BCberfall"
r=requests.get(u,timeout=30,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
s=BeautifulSoup(r.text,"html.parser")
for a in s.find_all("a",href=True):
    label=" ".join(a.get_text(" ",strip=True).split())
    href=urljoin(u,a["href"])
    if label.isdigit() or "Nächste" in label or "Weiter" in label:
        print(repr(label),href)

# trigger
