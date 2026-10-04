"""Kirim PDF sertifikat yang sudah jadi ke email pemiliknya (satu email per pemilik, semua sertifikatnya dilampirkan).

    ~/.venvs/mcfbooth/bin/python alat/kirim_sertifikat.py                 # daftar yang akan dikirim, tanpa mengirim
    ~/.venvs/mcfbooth/bin/python alat/kirim_sertifikat.py --uji a@b.com   # kirim satu contoh ke alamat itu, tanpa mencatat
    ~/.venvs/mcfbooth/bin/python alat/kirim_sertifikat.py --kirim         # kirim sungguhan
    ... --tahan 132,097C                                                  # lewati nomor urut atau label ini

PDF diambil dari folder "siap cetak" di Drive, pemilik dan hewan dari basis data reg ulang lokal, email dari VPS
(kolom email hanya ada di sana). Pengirim: dproductionorganizer@gmail.com lewat Gmail API (token di VPS).
Label yang sudah dikirim dicatat di data/email-sertifikat.json, jadi sertifikat yang menyusul dikirim di putaran
berikutnya tanpa mengulang yang lama.
"""
import base64, io, json, re, subprocess, sys, urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))
from app import server  # noqa: E402,F401
from app import drive_client as d  # noqa: E402

CATAT = AKAR / "data" / "email-sertifikat.json"
VPS = "root@100.71.16.42"
DARI = ("Panitia Pet Blessing 2026", "dproductionorganizer@gmail.com")
TOKEN_VPS = "/root/.hermes/google_token_akun3_dproductionorganizer.json"


def sh(cmd, batas=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=batas, check=True).stdout.strip()


def hewan_lokal():
    """label -> {owner, pemilik, hewan}, dan owner -> semua label hewannya."""
    out = sh(["docker", "exec", "pblokal-db", "sh", "-c",
              'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "|" -c "select c.arrival_number, p.sticker_letter, p.owner_id, o.name, p.name '
              "from api.pets p join api.checkins c on c.owner_id = p.owner_id and c.post = 'reg_ulang' join api.owners o on o.id = p.owner_id "
              'where c.arrival_number is not null and p.sticker_letter is not null order by 1, 2"'])
    per_label, per_pemilik = {}, {}
    for l in out.split("\n"):
        no, huruf, owner, pemilik, hewan = l.split("|")
        label = f"{int(no):03d}{huruf}"
        per_label[label] = {"owner": owner, "pemilik": pemilik, "hewan": hewan}
        per_pemilik.setdefault(owner, []).append(label)
    return per_label, per_pemilik


def email_vps():
    out = sh(["ssh", "-o", "ConnectTimeout=15", VPS,
              "docker exec petblessing-db sh -c \"psql -U \\\"\\$POSTGRES_USER\\\" -d \\\"\\$POSTGRES_DB\\\" -At -F '|' -c "
              "\\\"select id, email from api.owners where email like '%@%'\\\"\""])
    return dict(l.split("|") for l in out.split("\n") if "|" in l)


def akses():
    return sh(["ssh", "-o", "ConnectTimeout=15", VPS, "python3 -c \"import json,urllib.parse,urllib.request;"
               f"t=json.load(open('{TOKEN_VPS}'));"
               "d=urllib.parse.urlencode({'client_id':t['client_id'],'client_secret':t['client_secret'],'refresh_token':t['refresh_token'],'grant_type':'refresh_token'}).encode();"
               "print(json.loads(urllib.request.urlopen(urllib.request.Request(t['token_uri'],data=d),timeout=30).read())['access_token'])\""])


def daftar(butir):
    return butir[0] if len(butir) == 1 else ", ".join(butir[:-1]) + " dan " + butir[-1]


def isi(pemilik, kirim, belum):
    """kirim/belum: [(label, nama hewan)]."""
    nama = [h for _, h in kirim]
    baris = [f"Halo Kak {pemilik},", "",
             f"Terima kasih sudah hadir bersama {daftar(nama)} di Pet Blessing 2026, Paroki St. Vincentius a Paulo Malang. Senang sekali bisa ikut mendoakan{" mereka" if len(nama) > 1 else "nya"}.", "",
             "Terlampir sertifikat pemberkatannya:" if len(kirim) > 1 else f"Terlampir sertifikat pemberkatan untuk {nama[0]} (nomor {kirim[0][0]})."]
    if len(kirim) > 1:
        baris += [f"{i}. {h} (nomor {l})" for i, (l, h) in enumerate(kirim, 1)]
    baris += ["", "Berkasnya berbentuk PDF, jadi bisa disimpan di ponsel atau dicetak sendiri."]
    if belum:
        baris += ["", f"Sertifikat untuk {daftar([h for _, h in belum])} masih kami siapkan dan akan menyusul lewat email ini juga."]
    baris += ["", "Kalau ada nama yang kurang tepat atau fotonya tertukar, balas saja email ini supaya kami perbaiki.", "",
              "Salam hangat,", "Panitia Pet Blessing 2026"]
    return f"Sertifikat Pet Blessing 2026 untuk {daftar(nama)}", "\n".join(baris)


def kirim_email(token, tujuan, judul, teks, lampiran):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = formataddr(DARI), tujuan, judul
    m.set_content(teks)
    for nama, data in lampiran:
        m.add_attachment(data, maintype="application", subtype="pdf", filename=nama)
    req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                                 data=json.dumps({"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())["id"]


def unduh(svc, fid):
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=fid))
    selesai = False
    while not selesai:
        _, selesai = dl.next_chunk()
    return buf.getvalue()


def main():
    uji = sys.argv[sys.argv.index("--uji") + 1] if "--uji" in sys.argv else None
    tahan = set(sys.argv[sys.argv.index("--tahan") + 1].upper().split(",")) if "--tahan" in sys.argv else set()
    tahan = {f"{int(re.match(r'\d+', t).group()):03d}{t.lstrip('0123456789')}" for t in tahan}
    sungguhan = "--kirim" in sys.argv
    sudah = json.load(open(CATAT)) if CATAT.exists() else {}
    per_label, per_pemilik = hewan_lokal()
    email = email_vps()
    svc = d._svc()
    pdf = {}
    for f in sorted(svc.files().list(q="properties has { key='siap_cetak' and value='1' } and trashed=false",
                                     fields="files(id,name,modifiedTime)", pageSize=1000).execute()["files"], key=lambda f: f["modifiedTime"]):
        m = re.match(r"(\d{3}[A-Z])_", f["name"])
        if m:
            pdf[m.group(1)] = f          # yang terbaru menang
    token = akses() if (uji or sungguhan) else None
    terkirim = tanpa_email = 0
    for owner, labels in per_pemilik.items():
        siap = [l for l in labels if l in pdf and l not in sudah.get(owner, []) and l not in tahan and l[:3] not in tahan]
        if not siap:
            continue
        pemilik = per_label[siap[0]]["pemilik"]
        if owner not in email:
            tanpa_email += 1
            print(f"TANPA EMAIL  {siap[0][:3]} {pemilik}: {', '.join(siap)}")
            continue
        belum = [(l, per_label[l]["hewan"]) for l in labels if l not in siap and l not in sudah.get(owner, [])]
        judul, teks = isi(pemilik, [(l, per_label[l]["hewan"]) for l in siap], belum)
        print(f"{'KIRIM' if sungguhan else 'akan dikirim'}  {siap[0][:3]} {pemilik} <{email[owner]}>: {', '.join(siap)}" + (f" | menyusul {', '.join(l for l, _ in belum)}" if belum else ""))
        if not (uji or sungguhan):
            continue
        lampiran = [(f"Sertifikat Pet Blessing 2026 {per_label[l]['hewan']}.pdf", unduh(svc, pdf[l]["id"])) for l in siap]
        try:
            kirim_email(token, uji or email[owner], judul, teks, lampiran)
        except Exception as e:
            print("   GAGAL:", str(e)[:160])
            continue
        if uji:
            return print("contoh terkirim ke", uji, "\n\n" + judul + "\n\n" + teks)
        sudah.setdefault(owner, []).extend(siap)
        json.dump(sudah, open(CATAT, "w"), indent=1)
        terkirim += 1
    print(f"selesai: {terkirim} email terkirim, {tanpa_email} pemilik tanpa email")


main()
