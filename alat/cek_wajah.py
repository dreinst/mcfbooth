"""Lembar banding untuk hewan yang baru dipilah: foto pendaftaran (dari VPS) di samping foto yang ditetapkan.
Hasilnya /tmp/kw-pindah/wajah/cek-<label>.jpg, untuk dilihat lalu dinilai cocok atau tidak.

    ~/.venvs/mcfbooth/bin/python alat/cek_wajah.py          # semua pemilahan yang belum dicek
    ~/.venvs/mcfbooth/bin/python alat/cek_wajah.py --tandai  # tandai semuanya sudah dicek (setelah dilihat)
"""
import base64, io, json, re, subprocess, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw, ImageFont, ImageOps  # noqa: E402
from app import server  # noqa: E402,F401
from app import drive_client as d  # noqa: E402

W = Path("/tmp/kw-pindah/wajah")
CATAT = W / "sudah-dicek.json"
W.mkdir(parents=True, exist_ok=True)


def papan():
    hasil = {}
    for b in json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/pilah/papan", timeout=40).read())["sesi"]:
        hasil[f"mac:{b['id']}:{b['label']}"] = b
    w = subprocess.run(["ssh", "-o", "ConnectTimeout=10", "windows", "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\Public\\jaga-booth.ps1"],
                       capture_output=True, text=True, timeout=60).stdout.split("\n")[0]
    try:
        for b in json.loads(w)["sesi"]:
            hasil[f"win:{b['id']}:{b['label']}"] = b
    except Exception:
        print("booth Windows tidak terbaca")
    return hasil


def foto_daftar(label):
    """Foto pendaftaran hewan berlabel '077B' dari VPS (lewat nomor urut dan huruf di basis data lokal)."""
    nomor, huruf = int(label[:-1]), label[-1]
    pid = subprocess.run(["docker", "exec", "pblokal-db", "sh", "-c",
                          f"psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -At -c \"select p.id from api.pets p join api.checkins c on c.owner_id = p.owner_id and c.post = 'reg_ulang' where c.arrival_number = {nomor} and p.sticker_letter = '{huruf}' limit 1\""],
                         capture_output=True, text=True, timeout=30).stdout.strip()
    if not re.fullmatch(r"[0-9a-f-]{36}", pid):
        return None
    b64 = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "root@100.71.16.42",
                          f"docker exec petblessing-db sh -c \"psql -U \\\"\\$POSTGRES_USER\\\" -d \\\"\\$POSTGRES_DB\\\" -At -c \\\"select split_part(photo_base64, chr(44), 2) from api.pets where id='{pid}'\\\"\""],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        return ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(b64)))).convert("RGB") if len(b64) > 100 else None
    except Exception:
        return None


def huruf(u):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", u)
    except OSError:
        return ImageFont.load_default()


def main():
    sudah = set(json.load(open(CATAT))) if CATAT.exists() else set()
    kini = papan()
    baru = {k: b for k, b in kini.items() if k not in sudah}
    if "--tandai" in sys.argv:
        # Hanya yang lembarnya sudah dibuat (dan dilihat) yang ditandai; pemilahan yang muncul sesudahnya menunggu giliran.
        dilihat = set(json.load(open(W / "baru-dilihat.json"))) if (W / "baru-dilihat.json").exists() else set()
        json.dump(sorted(dilihat | sudah), open(CATAT, "w"))
        return print("ditandai sudah dicek:", sorted(dilihat))
    svc, SEL = d._svc(), 420
    for k, b in baru.items():
        fid = re.search(r"folders/([^/?]+)", b["folder_link"]).group(1)
        foto = svc.files().list(q=f"'{fid}' in parents and trashed=false and mimeType contains 'image/' and not name contains '{b['label']}_'",
                                fields="files(id,name)", orderBy="name", pageSize=100).execute()["files"]
        reg = foto_daftar(b["label"])
        kartu = [("PENDAFTARAN", reg)]
        for f in foto[:9]:
            t = d.thumb_berkas(f["id"])
            if t:
                kartu.append((f["name"][-12:], ImageOps.exif_transpose(Image.open(io.BytesIO(t)))))
        kol = 5
        brs = (len(kartu) + kol - 1) // kol
        L = Image.new("RGB", (kol * SEL, 44 + brs * (SEL + 26)), "white")
        dr = ImageDraw.Draw(L)
        dr.text((8, 8), f"{b['label']} {b['hewan']} ({b['jenis']}), milik {b['pemilik']}, {len(foto)} foto, {k.split(':')[0]}, sertifikat {b['sertifikat']}", font=huruf(24), fill="black")
        for i, (nm, im) in enumerate(kartu):
            x, y = (i % kol) * SEL, 44 + (i // kol) * (SEL + 26)
            if im is None:
                dr.rectangle([x + 4, y + 4, x + SEL - 4, y + SEL - 4], outline="red", width=4)
                dr.text((x + 20, y + 180), "tidak ada foto\npendaftaran", font=huruf(24), fill="red")
            else:
                L.paste(ImageOps.fit(im.convert("RGB"), (SEL - 8, SEL - 8)), (x + 4, y + 4))
            dr.text((x + 6, y + SEL), nm, font=huruf(17), fill="#b3261e" if i == 0 else "black")
        tujuan = W / f"cek-{b['label']}.jpg"
        L.save(tujuan, quality=86)
        print(f"{k} | {b['label']} {b['hewan']} | {b['pemilik']} | {len(foto)} foto | pendaftaran {'ada' if reg else 'TIDAK ADA'} | {tujuan}")
    json.dump(sorted(baru), open(W / "baru-dilihat.json", "w"))
    if not baru:
        print("tidak ada pemilahan baru")


main()
