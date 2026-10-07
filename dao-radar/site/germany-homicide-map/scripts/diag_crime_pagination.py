import requests,re
from bs4 import BeautifulSoup
u="https://www.presseportal.de/blaulicht/st/Raub%C3%BCberfall"
r=requests.get(u,timeout=30,headers={"User-Agent":"Mozilla/5.0"})
r.raise_for_status()
print("FINAL",r.url,"LEN",len(r.text))
s=BeautifulSoup(r.text,"html.parser")
for tag in s.find_all(True):
    text=" ".join(tag.get_text(" ",strip=True).split())
    attrs=" ".join(f"{k}={v}" for k,v in tag.attrs.items())
    raw=str(tag)[:800]
    if re.search(r"pagination|pager|page|next|start|offset|Nächste|Weiter",text+" "+attrs,re.I):
        print("TAG",tag.name,"TEXT",repr(text[:120]),"ATTR",repr(attrs[:300]))
for m in re.finditer(r".{0,120}(?:pagination|pager|next|offset|start|page=|/page/).{0,180}",r.text,re.I|re.S):
    print("RAW",re.sub(r"\s+"," ",m.group(0))[:420])
