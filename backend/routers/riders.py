import shutil
import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import schemas
from database import get_db
from deps import current_user, notify, rider_user

router = APIRouter(tags=["riders"])


@router.get("/riders/available")
def available_riders(db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    rows = db.execute("""SELECT r.*, u.full_name, u.phone FROM riders r JOIN users u ON u.id=r.user_id
                         WHERE r.verified=1 AND r.active=1 ORDER BY r.last_seen DESC""").fetchall()
    return [{"id": r["id"], "name": r["full_name"], "phone": r["phone"], "plate": r["plate"],
             "photo": r["photo_path"], "lat": r["lat"], "lng": r["lng"],
             "last_seen": r["last_seen"]} for r in rows]


@router.post("/rider/profile")
async def rider_profile(dl_number: str = Form(""), plate: str = Form(""), photo: UploadFile = File(None),
                        db: sqlite3.Connection = Depends(get_db), user=Depends(rider_user)):
    photo_path = ""
    if photo is not None and photo.filename:
        ext = photo.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            raise HTTPException(400, "Photo must be jpg, png or webp")
        photo_path = f"/uploads/{uuid.uuid4().hex[:12]}.{ext}"
        import config
        from pathlib import Path as _P
        dest = config.UPLOAD_DIR / _P(photo_path).name
        with open(dest, "wb") as f:
            shutil.copyfileobj(photo.file, f)
    db.execute("""INSERT INTO riders (user_id, dl_number, plate, photo_path)
                  VALUES (?,?,?,?)
                  ON CONFLICT(user_id) DO UPDATE SET
                    dl_number=excluded.dl_number, plate=excluded.plate,
                    photo_path=CASE WHEN excluded.photo_path='' THEN riders.photo_path ELSE excluded.photo_path END""",
               (user["id"], dl_number.strip(), plate.strip(), photo_path))
    db.commit()
    admins = db.execute("SELECT id FROM users WHERE role='admin'").fetchall()
    for a in admins:
        notify(db, a["id"], "Rider profile submitted", f"{user['full_name']} submitted DL + photo - review and verify.")
    return {"ok": True, "photo": photo_path}


@router.get("/rider/me")
def my_rider_profile(db: sqlite3.Connection = Depends(get_db), user=Depends(rider_user)):
    r = db.execute("SELECT * FROM riders WHERE user_id=?", (user["id"],)).fetchone()
    if r is None:
        return {"registered": False}
    return {"registered": True, "dl_number": r["dl_number"], "plate": r["plate"],
            "photo": r["photo_path"], "verified": bool(r["verified"]), "active": bool(r["active"])}
