import os, json, re
from datetime import datetime, date
from collections import defaultdict
from anthropic import Anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ["TELEGRAM_TOKEN"]
API_KEY = os.environ["ANTHROPIC_API_KEY"]
FILE = "data.json"
client = Anthropic(api_key=API_KEY)

def load():
    return json.load(open(FILE)) if os.path.exists(FILE) else {}

def save(d):
    json.dump(d, open(FILE,"w"), ensure_ascii=False, indent=2)

def add(uid, t):
    d = load()
    d.setdefault(uid, {"tr":[]})["tr"].append(t)
    save(d)

def rp(n):
    return f"Rp {int(n):,}".replace(",",".")

def tanya(teks):
    try:
        r = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system='Ekstrak transaksi keuangan. Balas HANYA JSON. Jika transaksi: {"ok":true,"tipe":"pengeluaran atau pemasukan","jumlah":angka,"kat":"Makan/Transport/Belanja/Tagihan/Gaji/Lainnya","desc":"singkat"}. Jika bukan: {"ok":false,"msg":"balasan ramah"}',
            messages=[{"role":"user","content":teks}]
        )
        raw = re.sub(r"```json|```","",r.content[0].text).strip()
        return json.loads(raw)
    except:
        return {"ok":False,"msg":"Maaf ada error, coba lagi!"}

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        f"👋 Halo *{u.effective_user.first_name}*!\n\n"
        "Ketik transaksi langsung:\n"
        "• `makan siang 35rb`\n"
        "• `gajian 5 juta`\n"
        "• `bayar listrik 250rb`\n\n"
        "/laporan — laporan bulan ini\n"
        "/hari — transaksi hari ini\n"
        "/hapus — hapus transaksi terakhir",
        parse_mode="Markdown"
    )

async def laporan(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = str(u.effective_user.id)
    tr = load().get(uid,{}).get("tr",[])
    now = datetime.now()
    bl = ["","Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"]
    f = [t for t in tr if datetime.fromisoformat(t["w"]).month==now.month and datetime.fromisoformat(t["w"]).year==now.year]
    if not f:
        await u.message.reply_text("📭 Belum ada transaksi bulan ini.")
        return
    masuk = sum(t["j"] for t in f if t["tipe"]=="pemasukan")
    keluar = sum(t["j"] for t in f if t["tipe"]=="pengeluaran")
    kat = defaultdict(int)
    for t in f:
        if t["tipe"]=="pengeluaran": kat[t["kat"]]+=t["j"]
    baris = [f"📊 *Laporan {bl[now.month]} {now.year}*",f"{'─'*24}",
             f"💰 Pemasukan: *{rp(masuk)}*",f"💸 Pengeluaran: *{rp(keluar)}*",f"{'─'*24}"]
    for k,v in sorted(kat.items(),key=lambda x:-x[1]):
        baris.append(f"  • {k}: {rp(v)}")
    baris.append(f"\n{'✅' if masuk>=keluar else '⚠️'} *Saldo: {rp(masuk-keluar)}*")
    await u.message.reply_text("\n".join(baris), parse_mode="Markdown")

async def hari(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = str(u.effective_user.id)
    tr = load().get(uid,{}).get("tr",[])
    hi = date.today().isoformat()
    f = [t for t in tr if t["w"].startswith(hi)]
    if not f:
        await u.message.reply_text("📭 Belum ada transaksi hari ini.")
        return
    masuk = sum(t["j"] for t in f if t["tipe"]=="pemasukan")
    keluar = sum(t["j"] for t in f if t["tipe"]=="pengeluaran")
    baris = ["📅 *Transaksi Hari Ini*\n"]
    for i,t in enumerate(f,1):
        ikon = "💰" if t["tipe"]=="pemasukan" else "💸"
        jam = datetime.fromisoformat(t["w"]).strftime("%H:%M")
        baris.append(f"{i}. {ikon} {t['desc'].capitalize()} — *{rp(t['j'])}* _{jam}_")
    baris += [f"\n{'─'*22}",f"📊 Saldo: *{rp(masuk-keluar)}*"]
    await u.message.reply_text("\n".join(baris), parse_mode="Markdown")

async def hapus(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = str(u.effective_user.id)
    d = load()
    tr = d.get(uid,{}).get("tr",[])
    if not tr:
        await u.message.reply_text("❌ Tidak ada transaksi.")
        return
    x = tr.pop()
    save(d)
    await u.message.reply_text(f"🗑 Dihapus: *{x['desc'].capitalize()}* — {rp(x['j'])}", parse_mode="Markdown")

async def pesan(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = str(u.effective_user.id)
    h = tanya(u.message.text.strip())
    if not h.get("ok"):
        await u.message.reply_text(h.get("msg","Ketik transaksi ya, contoh: *makan 25rb*"), parse_mode="Markdown")
        return
    t = {"tipe":h["tipe"],"j":h["jumlah"],"kat":h["kat"],"desc":h["desc"],"w":datetime.now().isoformat()}
    add(uid, t)
    tr = load().get(uid,{}).get("tr",[])
    hi = date.today().isoformat()
    saldo = sum(x["j"] if x["tipe"]=="pemasukan" else -x["j"] for x in tr if x["w"].startswith(hi))
    ikon = "💰" if h["tipe"]=="pemasukan" else "💸"
    await u.message.reply_text(
        f"{ikon} *{h['desc'].capitalize()}* dicatat!\n"
        f"Jumlah: *{rp(h['jumlah'])}*\n"
        f"Kategori: {h['kat']}\n"
        f"─────────────────\n"
        f"Saldo hari ini: *{rp(saldo)}*",
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("laporan", laporan))
    app.add_handler(CommandHandler("hari", hari))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, pesan))
    print("Bot aktif!")
    app.run_polling(drop_pending_updates=True)
