"""
Seeds a handful of demo HCPs on startup, if the table is empty. Purely for demoing/testing
the Log Interaction screen without having to manually add doctors first.
"""
from app.db.session import SessionLocal
from app.models.models import HCP

SEED_DOCTORS = [
    {
        "name": "Dr. Anita Rao",
        "specialty": "Cardiology",
        "hospital": "Apollo Hospitals",
        "email": "anita.rao@apollohospitals.example",
        "phone": "+91-9840012345",
        "preferred_channel": "in_person",
        "notes": "Prefers morning slots. Interested in cardiovascular trial data.",
    },
    {
        "name": "Dr. Rohan Mehta",
        "specialty": "Endocrinology",
        "hospital": "Fortis Hospital",
        "email": "rohan.mehta@fortis.example",
        "phone": "+91-9820098765",
        "preferred_channel": "video_call",
        "notes": "Busy schedule; video calls work best.",
    },
    {
        "name": "Dr. Priya Nair",
        "specialty": "Oncology",
        "hospital": "Tata Memorial Hospital",
        "email": "priya.nair@tmh.example",
        "phone": "+91-9873011223",
        "preferred_channel": "in_person",
        "notes": "Requests published efficacy data before samples.",
    },
    {
        "name": "Dr. Suresh Iyer",
        "specialty": "Nephrology",
        "hospital": "AIIMS Delhi",
        "email": "suresh.iyer@aiims.example",
        "phone": "+91-9911022334",
        "preferred_channel": "call",
        "notes": None,
    },
    {
        "name": "Dr. Kavita Desai",
        "specialty": "Pulmonology",
        "hospital": "Manipal Hospital",
        "email": "kavita.desai@manipal.example",
        "phone": "+91-9945566778",
        "preferred_channel": "email",
        "notes": "Prefers email follow-ups over calls.",
    },
    {
        "name": "Dr. Arjun Menon",
        "specialty": "General Medicine",
        "hospital": "CMC Vellore",
        "email": "arjun.menon@cmcvellore.example",
        "phone": "+91-9080011224",
        "preferred_channel": "in_person",
        "notes": None,
    },
]


def seed_doctors():
    db = SessionLocal()
    try:
        if db.query(HCP).count() == 0:
            for doc in SEED_DOCTORS:
                db.add(HCP(**doc))
            db.commit()
    finally:
        db.close()
