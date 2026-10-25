"""Import team-supplied course instructor notes with explicit provenance."""
import hashlib
import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'datafiles/course_faculty_assignments.json'


def extract_records(faculty_profiles=None, path=SOURCE):
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Course faculty source not found: {path}')
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    raw=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw,list):
        raise ValueError('Course faculty source must be a JSON list')
    profiles=faculty_profiles
    if profiles is None:
        profiles=json.loads((ROOT/'datafiles/academic/faculty_profiles.json').read_text(encoding='utf-8'))
    by_name={p['name'].strip().casefold():p for p in profiles}
    records=[]
    for index,item in enumerate(raw,1):
        code=str(item.get('course_code','')).strip().upper()
        name=str(item.get('faculty_name','')).strip()
        role=str(item.get('role','Instructor')).strip()
        if not code or not name:
            raise ValueError(f'Course faculty row {index} needs course_code and faculty_name')
        profile=by_name.get(name.casefold())
        records.append({
            'record_id':str(uuid.uuid5(uuid.NAMESPACE_URL,
                f'course-faculty:{source_hash}:{index}:{code}:{name}')),
            'course_code':code,
            'faculty_name':name,
            'faculty_id':profile.get('faculty_id') if profile else None,
            'role':role,
            'provided_by':item.get('provided_by') or 'user supplied',
            'applicability':item.get('applicability') or 'user_supplied_unverified',
            'evidence':{
                'source_version_id':source_hash,
                'path':path.relative_to(ROOT).as_posix(),
                'row':index,
                'locator':f'$[{index-1}]',
                'quote':f"{code} | {role}: {name}",
            },
        })
    return records
