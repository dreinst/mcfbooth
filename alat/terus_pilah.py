"""Penerus TCP kecil: membuka booth di Mac ini (127.0.0.1:8000) hanya di alamat Tailscale Mac, supaya VPS bisa
meneruskan alamat web Meja pilah ke sini. Wifi lokasi tidak ikut dibuka, karena Meja pilah tidak punya login;
kata sandi dipasang di VPS (Traefik basicAuth, berkas pilah-pb.yaml).

Dijalankan LaunchAgent com.dpro.pb-pilah-web. Pakai: terus_pilah.py <alamat-tailscale> <port>
"""
import asyncio
import sys

ALAMAT, PORT = sys.argv[1], int(sys.argv[2])
TUJUAN = ("127.0.0.1", 8000)


async def salin(dari, ke):
    try:
        while data := await dari.read(65536):
            ke.write(data)
            await ke.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        ke.close()


async def layani(masuk_r, masuk_w):
    try:
        keluar_r, keluar_w = await asyncio.open_connection(*TUJUAN)
    except OSError:
        masuk_w.close()
        return
    await asyncio.gather(salin(masuk_r, keluar_w), salin(keluar_r, masuk_w))


async def main():
    server = await asyncio.start_server(layani, ALAMAT, PORT)
    print(f"meneruskan {ALAMAT}:{PORT} ke {TUJUAN[0]}:{TUJUAN[1]}", flush=True)
    async with server:
        await server.serve_forever()


asyncio.run(main())
