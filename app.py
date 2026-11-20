import streamlit as st
import subprocess
import os
import json
from faster_whisper import WhisperModel
from google import genai
from google.genai import types

st.set_page_config(page_title="AI Multi-Clipper YouTube", layout="centered")
st.title("🎬 YouTube to Multi-Clips + Auto CC")
st.write("Tempel 1 link YouTube, AI otomatis mencari momen viral & membuat banyak klip 9:16.")

gemini_key = st.text_input("Masukkan Gemini API Key:", type="password")
yt_url = st.text_input("Tempel Link YouTube:")
num_clips = st.slider("Jumlah klip yang ingin dihasilkan:", 2, 5, 3)

def format_ts(seconds):
    hrs, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{int(hrs):02d}:{int(mins):02d}:{int(secs):02d},{millis:03d}"

if st.button("🚀 Proses Jadi Banyak Klip") and yt_url and gemini_key:
    video_file = "full_video.mp4"
    
    with st.spinner("1/4 Mengunduh video dari YouTube..."):
        subprocess.run([
            "yt-dlp", "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/mp4",
            "-o", video_file, yt_url
        ], check=True)

    with st.spinner("2/4 Membuat transkrip penuh & deteksi kata (Whisper AI)..."):
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(video_file, word_timestamps=True)
        
        full_transcript = ""
        all_words = []
        for seg in segments:
            full_transcript += f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}\n"
            for w in seg.words:
                all_words.append({"word": w.word.strip().upper(), "start": w.start, "end": w.end})

    with st.spinner(f"3/4 AI sedang memilih {num_clips} momen paling menarik..."):
        client = genai.Client(api_key=gemini_key)
        prompt = f"""
        Analisis transkrip video berikut dan pilih {num_clips} segmen paling menarik, mengejutkan, atau berpotensi viral untuk dijadikan klip pendek (durasi masing-masing 25-45 detik).
        Kembalikan HANYA format JSON list seperti ini tanpa teks tambahan:
        [{{"title": "judul_singkat", "start": 12.5, "end": 45.0}}]
        
        Transkrip:
        {full_transcript[:15000]}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        moments = json.loads(response.text)

    with st.spinner("4/4 Merender semua klip & menempelkan teks CC..."):
        generated_files = []
        for idx, m in enumerate(moments):
            start_t = float(m["start"])
            end_t = float(m["end"])
            duration = end_t - start_t
            srt_name = f"clip_{idx}.srt"
            raw_clip = f"raw_{idx}.mp4"
            final_clip = f"final_clip_{idx+1}.mp4"

            with open(srt_name, "w", encoding="utf-8") as srt:
                w_idx = 1
                for w in all_words:
                    if start_t <= w["start"] <= end_t:
                        rel_start = format_ts(max(0, w["start"] - start_t))
                        rel_end = format_ts(max(0, w["end"] - start_t))
                        srt.write(f"{w_idx}\n{rel_start} --> {rel_end}\n{w['word']}\n\n")
                        w_idx += 1

            subprocess.run([
                "ffmpeg", "-y", "-ss", str(start_t), "-t", str(duration),
                "-i", video_file, "-vf", "crop=ih*(9/16):ih,scale=1080:1920",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", raw_clip
            ], check=True)

            style = "FontName=Arial,FontSize=18,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=10"
            subprocess.run([
                "ffmpeg", "-y", "-i", raw_clip,
                "-vf", f"subtitles={srt_name}:force_style='{style}'",
                "-c:a", "copy", final_clip
            ], check=True)

            generated_files.append((m.get("title", f"Klip {idx+1}"), final_clip))

    st.success(f"Selesai! Berhasil membuat {len(generated_files)} klip otomatis.")
    for title, filepath in generated_files:
        st.subheader(f"🎬 {title}")
        st.video(filepath)
        with open(filepath, "rb") as f:
            st.download_button(f"⬇️ Download {title}", f, file_name=filepath, key=filepath)
