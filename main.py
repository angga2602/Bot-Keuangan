import os
import json
import re
from datetime import datetime, date
from collections import defaultdict
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def tambah_transaksi(uid, t):
    data = load_data()
    data.setdefault(uid, {"transaksi": []})
    data[uid]["transaksi"].append(t)
    save_data(data)

def format_rp(n):
    return f"Rp {int(n):,}".replace(",", ".")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM = """Kamu asisten pencatat keuangan. Ekstrak info dari pesan dan balas HANYA JSON.

Jika transaksi keuangan:
{"terdeteksi":true,"tipe":"pengeluaran atau pemasukan","jumlah":angka,"kategori":"Makan/Transport/Belanja/Hiburan/Kesehatan/Tagihan/Gaji/Freelance/Lainnya","deskripsi":"singkat"}

Jika bukan transaksi:
{"terdeteksi":false,"pesan":"balasan ramah bahasa Indonesia"}

Contoh:
"makan 25rb" -> {"terdeteksi":true,"tipe":"pengeluaran","jumlah":25000,"kategori":"Makan","deskripsi":"makan"}
"gaji 5jt" -> {"terdeteksi":true,"tipe":"pemasukan","jumlah":5000000,"kategori":"Gaji","deskripsi":"gaji"}"""

def tanya_claude(teks):
    try:
        r = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=SYSTEM,
            messages=[{"role": "user", "content": teks}]
        )
        raw = r.content[0].text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except:
        return {"terdeteksi": False, "pesan": "Maaf ada error, coba lagi ya!"}

def laporan_bulan(uid):
    data = load_data().get(uid, {}).get("transaksi", [])
    now = datetime.now()
    bulan_nama = ["","Januari","Februari","Maret","April","Mei","Juni",
                  "Juli","Agustus","September","Oktober","November","Desember"]
    filtered = [t for t in data
                if datetime.fromisoformat(t["waktu"]).month == now.month
                and datetime.fromisoformat(t["waktu"]).year == now.year]
    if not filtered:
        return "📭 Belum ada transaksi bulan ini."
    masuk = sum(t["jumlah"] for t in filtered if t["tipe"] == "pemasukan")
    keluar = sum(t["jumlah"] for t in filtered if t["tipe"] == "pengeluaran")
    saldo = masuk - keluar
    kat = defaultdict(int)
    for t in filtered:
        if t["tipe"] == "pengeluaran":
            kat[t["kategori"]] += t["jumlah"]
    baris = [
        f"📊 *Laporan {bulan_nama[now.month]} {now.year}*",
        f"{'─'*26}",
        f"💰 Pemasukan: *{format_rp(masuk)}*",
        f"💸 Pengeluaran: *{format_rp(keluar)}*",
        f"{'─'*26}",
    ]
    if kat:
        baris.append("📂 *Rincian Pengeluaran:*")
        for k, v in sorted(kat.items(), key=lambda x: -x[1]):
            pct = v/keluar*100 if keluar else 0
            baris.append(f"  • {k}: {format_rp(v)} ({pct:.0f}%)")
        baris.append(f"{'─'*26}")
    ikon = "✅" if saldo >= 0 else "⚠️"
    baris.append(f"{ikon} *Saldo: {format_rp(saldo)}*")
    baris.append(f"📈 Total transaksi: {len(filtered)}")
    return "\n".join(baris)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Halo *{update.effective_user.first_name}*!\n\n"
        "Saya bot pencatat keuangan kamu 💰\n\n"
        "*Cara pakai — ketik langsung:*\n"
        "• `makan siang 35rb`\n"
        "• `gajian 5 juta`\n"
        "• `bayar listrik 250rb`\n"
        "• `grab 18000`\n\n"
        "📋 *Perintah:*\n"
        "/laporan — laporan bulan ini\n"
        "/hari — transaksi hari ini\n"
        "/hapus — hapus transaksi terakhir",
        parse_mode="Markdown"
    )

async def laporan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    await update.message.reply_text("⏳ Menyiapkan laporan...")
    await update.message.reply_text(laporan_bulan(uid), parse_mode="Markdown")

async def hari(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data().get(uid, {}).get("transaksi", [])
    hari_ini = date.today().isoformat()
    tr = [t for t in data if t["waktu"].startswith(hari_ini)]
    if not tr:
        await update.message.reply_text("📭 Belum ada transaksi hari ini.")
        return
    masuk = sum(t["jumlah"] for t in tr if t["tipe"] == "pemasukan")
    keluar = sum(t["jumlah"] for t in tr if t["tipe"] == "pengeluaran")
    baris = ["📅 *Transaksi Hari Ini*\n"]
    for i, t in enumerate(tr, 1):
        ikon = "💰" if t["tipe"] == "pemasukan" else "💸"
        jam = datetime.fromisoformat(t["waktu"]).strftime("%H:%M")
        baris.append(f"{i}. {ikon} {t['deskripsi'].capitalize()} — *{format_rp(t['jumlah'])}*  _{jam}_")
    baris += [f"\n{'─'*24}",
              f"💰 Masuk: {format_rp(masuk)}",
              f"💸 Keluar: {format_rp(keluar)}",
              f"📊 Saldo: *{format_rp(masuk-keluar)}*"]
    await update.message.reply_text("\n".join(baris), parse_mode="Markdown")

async def hapus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    tr = data.get(uid, {}).get("transaksi", [])
    if not tr:
        await update.message.reply_text("❌ Tidak ada transaksi untuk dihapus.")
        return
    dihapus = tr.pop()
    save_data(data)
    await update.message.reply_text(
        f"🗑 Dihapus: *{dihapus['deskripsi'].capitalize()}* — {format_rp(dihapus['jumlah'])}",
        parse_mode="Markdown"
    )

async def pesan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    teks = update.message.text.strip()
    hasil = tanya_claude(teks)
    if not hasil.get("terdeteksi"):
        await update.message.reply_text(
            hasil.get("pesan", "Ketik nominal transaksi ya, contoh: *makan 25rb*"),
            parse_mode="Markdown"
        )
        return
    t = {
        "tipe": hasil["tipe"],
        "jumlah": hasil["jumlah"],
        "kategori": hasil["kategori"],
        "deskripsi": hasil["deskripsi"],
        "waktu": datetime.now().isoformat(),
    }
    tambah_transaksi(uid, t)
    data = load_data().get(uid, {}).get("transaksi", [])
    hari_ini = date.today().isoformat()
    saldo = sum(
        x["jumlah"] if x["tipe"] == "pemasukan" else -x["jumlah"]
        for x in data if x["waktu"].startswith(hari_ini)
    )
    ikon = "💰" if hasil["tipe"] == "pemasukan" else "💸"
    await update.message.reply_text(
        f"{ikon} *{hasil['deskripsi'].capitalize()}* dicatat!\n"
        f"Jumlah: *{format_rp(hasil['jumlah'])}*\n"
        f"Kategori: {hasil['kategori']}\n"
        f"─────────────────\n"
        f"Saldo hari ini: *{format_rp(saldo)}*",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("laporan", laporan))
    app.add_handler(CommandHandler("hari", hari))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, pesan))
    print("Bot aktif!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
