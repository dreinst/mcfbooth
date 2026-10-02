"""Folder Pet Blessing yang disiapkan dengan nomor pendaftaran diganti nama ke nomor urut
saat sesi dimulai, tanpa membuat folder kembar (termasuk dua pemilik bernama sama).
    python uji/uji_ganti_nama.py
"""
import os, sys, tempfile
os.environ.update(MCF_DRIVE_PALSU="1", DRIVE_FOLDER_RAW_ID="palsu-raw", DRIVE_FOLDER_SERTIFIKAT_ID="palsu-sert",
                  MCF_DB=tempfile.mktemp(suffix=".db"))
sys.path.insert(0, ".")
from app import db, drive_client as d, petblessing as pb
db.siapkan()
P = d._palsu
# Disiapkan sebelum hari-H (nomor pendaftaran): Lita 141 dan Lita 152.
for nd, hewan in [(141, "A Moana (Anjing)"), (152, "A Mochi (Anjing)")]:
    o = P.buat_folder(f"{nd:03d} Lita", "palsu-raw")["id"]; P.buat_folder(hewan, o)
    P.buat_folder(f"{nd:03d} Lita", "palsu-sert")
s1 = {"nomor": 152, "nomor_daftar": 141, "pemilik": "Lita", "huruf": "A", "hewan": "Moana", "jenis": "Anjing"}
f = d.buat_folder_sesi(pb.folder_hewan(s1), pb.folder_pemilik(s1), pb.folder_hewan(s1, True), pb.folder_pemilik(s1, True))
nama = lambda i: P.folder[i]["nama"]; induk = lambda i: P.folder[i]["parent"]
ok = [nama(f["id"]) == "152A Moana (Anjing)", nama(induk(f["id"])) == "152 Lita",
      sum(1 for x in P.folder.values() if x["parent"] == "palsu-raw") == 2]
# Lita kedua (nomor pendaftaran 152) tetap memakai foldernya sendiri walau namanya kini sama.
lita2 = [k for k, x in P.folder.items() if x["nama"] == "A Mochi (Anjing)"][0]
ok.append(nama(induk(lita2)) == "152 Lita" and induk(lita2) != induk(f["id"]))
srt = d.folder_sertifikat(pb.folder_pemilik(s1), f["id"], pb.folder_pemilik(s1, True))
ok.append(nama(srt) == "152 Lita" and sum(1 for x in P.folder.values() if x["parent"] == "palsu-sert") == 2)
# Sesi kedua hewan yang sama: tidak membuat folder baru.
f2 = d.buat_folder_sesi(pb.folder_hewan(s1), pb.folder_pemilik(s1), pb.folder_hewan(s1, True), pb.folder_pemilik(s1, True))
ok.append(f2["id"] == f["id"])
print(ok); sys.exit(0 if all(ok) else 1)
