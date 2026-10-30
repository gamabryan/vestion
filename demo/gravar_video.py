"""Grava um vídeo de apresentação do Vestion (para LinkedIn) com dados de exemplo.

Abre a central em tela cheia, roda um roteiro (resumo do dia, um lembrete e uma reunião), grava a tela
com ffmpeg e junta a voz do Vestion depois, no tempo certo. Nada da sua conta Google aparece.

    .venv\\Scripts\\python demo\\gravar_video.py

Durante a gravação (cerca de 1 minuto e meio), não mexa no PC. O vídeo sai em demo\\saida\\vestion.mp4.
"""
import json
import re
import subprocess
import sys
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import webview

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lia.audio.tts import ENVELOPE_FRAME_MS, speech_envelope, synth_edge  # noqa: E402
from lia.briefing import briefing_text, spoken_time  # noqa: E402
from lia.panels import agenda_panel, gmail_panel, reminders_panel  # noqa: E402
from lia.ui_window import CentralWindow  # noqa: E402

VOICE = "pt-BR-AntonioNeural"
OUT = Path(__file__).with_name("saida")
SR = 44100

# ---- dados de exemplo (fictícios) ----------------------------------------------------
NOW = datetime.now().astimezone()
TODAY = NOW.replace(second=0, microsecond=0)


def at(h, m=0, days=0):
    return (TODAY + timedelta(days=days)).replace(hour=h, minute=m)


MEETING = at(min(NOW.hour + 3, 20))
EVENTS = [
    {"id": "1", "titulo": "Daily com o time", "inicio": at(9, 30), "fim": at(9, 45), "dia_todo": False},
    {"id": "2", "titulo": "Almoço com a Ana", "inicio": at(12, 30), "fim": at(13, 30), "dia_todo": False},
    {"id": "3", "titulo": "Revisão do projeto", "inicio": at(17), "fim": at(18), "dia_todo": False},
]
NEW_EVENT = {"id": "4", "titulo": "Reunião com o time de produto", "inicio": MEETING,
             "fim": MEETING + timedelta(hours=1), "dia_todo": False}
MAILS = [
    {"de": "Mariana Costa", "assunto": "proposta comercial", "importante": True},
    {"de": "Carlos Lima", "assunto": "reunião de quinta"},
    {"de": "Financeiro", "assunto": "fechamento do mês"},
]
REMINDER_TODAY = {"id": "r1", "texto": "pagar o boleto da internet", "quando": at(19).isoformat()}
REMINDER_TASK = {"id": "r2", "texto": "comprar ração", "quando": None}
NEW_REMINDER = {"id": "r3", "texto": "enviar a proposta para a Mariana", "quando": at(10, days=1).isoformat()}


def groups(extra=()):
    return {"atrasados": [], "hoje": [REMINDER_TODAY], "proximos": list(extra), "sem_hora": [REMINDER_TASK]}


def agenda(events):
    return agenda_panel(sorted(events, key=lambda e: e["inicio"]))


# ---- roteiro --------------------------------------------------------------------------
BRIEFING = briefing_text(NOW, EVENTS, MAILS, groups())
SAY_REMINDER = "Pronto. Amanhã às dez da manhã eu te lembro de enviar a proposta para a Mariana."
SAY_MEETING = (f"Marquei a reunião com o time de produto hoje {spoken_time(MEETING)}. "
               "Já está na sua agenda.")
USER_REMINDER = "Vestion, me lembra amanhã às dez de enviar a proposta para a Mariana."
USER_MEETING = f"Marca uma reunião com o time de produto hoje {spoken_time(MEETING)}."

OVERLAY_CSS = """
#demo-title{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
 z-index:50;background:rgba(1,4,10,.82);transition:opacity 1.2s;pointer-events:none}
#demo-title h1{font-family:Orbitron;font-weight:800;font-size:96px;letter-spacing:.35em;color:var(--c);
 text-shadow:0 0 30px var(--c);margin-left:.35em}
#demo-title p{font-family:Rajdhani;font-size:30px;letter-spacing:.18em;color:var(--text);opacity:.85;margin-top:18px}
#demo-title small{font-family:Rajdhani;font-size:20px;letter-spacing:.2em;color:var(--c2);margin-top:26px}
#you{font-size:24px!important;opacity:1!important;color:var(--text)!important}
#demo-tab{position:fixed;left:50%;bottom:230px;transform:translateX(-50%);z-index:40;padding:10px 22px;
 border:1px solid var(--glass-border);border-radius:999px;background:rgba(10,30,45,.6);font-family:Rajdhani;
 font-size:20px;letter-spacing:.2em;color:var(--c);opacity:0;transition:opacity .3s}
#demo-tab b{border:1px solid var(--c);border-radius:6px;padding:1px 10px;margin-right:10px}
"""


def js_overlay(title, subtitle, small=""):
    return f"""(function(){{
      let s=document.getElementById('demo-style'); if(!s){{s=document.createElement('style');s.id='demo-style';
      s.textContent={json.dumps(OVERLAY_CSS)};document.head.appendChild(s);}}
      let d=document.getElementById('demo-title'); if(!d){{d=document.createElement('div');d.id='demo-title';
      document.body.appendChild(d);}}
      d.innerHTML='<h1>'+{json.dumps(title)}+'</h1><p>'+{json.dumps(subtitle)}+'</p><small>'+{json.dumps(small)}+'</small>';
      d.style.opacity=1;
      let t=document.getElementById('demo-tab'); if(!t){{t=document.createElement('div');t.id='demo-tab';
      t.innerHTML='<b>TAB</b>SEGURANDO · OUVINDO';document.body.appendChild(t);}}
    }})()"""


JS_HIDE_TITLE = "document.getElementById('demo-title').style.opacity=0"


def js_tab(on):
    return f"document.getElementById('demo-tab').style.opacity={1 if on else 0}"


# ---- áudio ----------------------------------------------------------------------------
def synth(text):
    audio, sr = synth_edge(text, VOICE)
    assert sr == SR, sr
    return audio, speech_envelope(audio, sr)


def write_wav(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# ---- gravação -------------------------------------------------------------------------
def main():
    OUT.mkdir(exist_ok=True)
    print("Gerando as falas...")
    lines = {"briefing": synth(BRIEFING), "reminder": synth(SAY_REMINDER), "meeting": synth(SAY_MEETING)}
    clips = []  # (horário do relógio em que a fala começou, áudio)
    raw = OUT / "tela.mkv"
    win = CentralWindow(lambda rid, ok: None)

    def run(w):
        w._loaded.wait(30)
        js = w.window.evaluate_js
        time.sleep(1.5)
        w.update_panel("agenda", agenda(EVENTS))
        w.update_panel("gmail", gmail_panel(MAILS, 3))
        w.update_panel("lembretes", reminders_panel(groups(), NOW))
        w.update_panel("sistema", {"cpu": 9, "mem": 41, "uso_plano": 12, "pedidos_hoje": 3, "limite": False})
        w.caption("")
        js(js_overlay("VESTION", "MEU ASSISTENTE DE VOZ PARA O PC", "CLAUDE · GMAIL · AGENDA · TAREFAS"))
        time.sleep(1.5)

        rec = subprocess.Popen([ffmpeg_exe(), "-hide_banner", "-y", "-f", "gdigrab", "-framerate", "30",
                                "-draw_mouse", "0", "-i", "desktop", "-c:v", "libx264", "-preset", "ultrafast",
                                "-crf", "16", "-copyts", str(raw)],
                               stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        time.sleep(3.5)

        def speak(name, caption):
            audio, env = lines[name]
            w.set_state("speaking")
            w.caption(caption)
            clips.append((time.time(), audio))
            w.speak(env, ENVELOPE_FRAME_MS)
            time.sleep(len(audio) / SR + 0.4)
            w.set_state("idle")

        def user(text):
            w.set_state("listening")
            js(js_tab(True))
            w.caption("")
            w.caption("", "user")
            words = text.split()
            for i in range(1, len(words) + 1):  # aparece enquanto "fala"
                w.caption(" ".join(words[:i]), "user")
                time.sleep(0.28)
            time.sleep(0.6)
            js(js_tab(False))
            w.set_state("thinking")
            time.sleep(1.6)

        js(JS_HIDE_TITLE)
        time.sleep(1.4)
        speak("briefing", BRIEFING)
        time.sleep(1.2)
        user(USER_REMINDER)
        w.update_panel("lembretes", reminders_panel(groups([NEW_REMINDER]), NOW))
        speak("reminder", SAY_REMINDER)
        time.sleep(1.2)
        user(USER_MEETING)
        w.update_panel("agenda", agenda(EVENTS + [NEW_EVENT]))
        speak("meeting", SAY_MEETING)
        time.sleep(1.5)
        js(js_overlay("VESTION", "FALO E ELE FAZ — NO MEU PRÓPRIO COMPUTADOR", "FEITO COM CLAUDE CODE"))
        time.sleep(4)

        rec.stdin.write(b"q")
        rec.stdin.flush()
        rec.wait(30)
        w.destroy()

    webview.start(run, win)
    build_video(raw, clips)


def first_frame_time(raw: Path) -> float:
    """Horário (relógio do PC) do primeiro quadro: o gdigrab carimba os quadros com a hora real."""
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-copyts", "-i", str(raw), "-vf", "showinfo",
                          "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.search(r"pts_time:([\d.]+)", out).group(1))


def build_video(raw: Path, clips):
    start = first_frame_time(raw)
    print(f"primeiro quadro em {start:.3f}")
    end = max(t - start + len(a) / SR for t, a in clips) + 10
    track = np.zeros(int(end * SR), dtype=np.float32)
    for t, audio in clips:
        i = int(round((t - start) * SR))
        track[i:i + len(audio)] += audio
    wav = OUT / "voz.wav"
    write_wav(wav, track * 0.95)
    final = OUT / "vestion.mp4"
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-i", str(wav),
                    "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "20", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-movflags", "+faststart", str(final)], check=True)
    print(f"Pronto: {final}")


if __name__ == "__main__":
    main()
