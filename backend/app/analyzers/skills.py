import re
from dataclasses import dataclass

from app.core.enums import ResumeVariant, RoleCategory

ECOSYSTEMS: dict[str, list[str]] = {
    "frontend": [
        "react",
        "next.js",
        "nextjs",
        "vue",
        "nuxt",
        "typescript",
        "javascript",
        "tailwind",
        "mui",
        "vuetify",
        "pwa",
        "service workers",
    ],
    "backend_js": ["node.js", "nodejs", "node", "express", "nestjs", "nest"],
    "database": ["postgresql", "postgres", "mongodb", "mysql", "redis"],
    "infra": ["docker", "github actions", "gitlab ci", "ci/cd", "vite", "nx", "npm", "minio"],
    "api": ["rest", "graphql", "websocket", "websockets", "mqtt", "swagger", "openapi", "firebase", "signalr", "sentry"],
}

CANONICAL = {
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node": "Node.js",
    "nestjs": "NestJS",
    "nest": "NestJS",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "react": "React",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
}


@dataclass(frozen=True)
class SkillMatch:
    matched: list[str]
    missing: list[str]
    ecosystem_hits: list[str]
    score: float
    resume_variant: str
    role_category: str


def extract_skills(text: str) -> list[str]:
    blob = text.lower()
    found: list[str] = []
    for skills in ECOSYSTEMS.values():
        for skill in skills:
            if _contains_skill(blob, skill) and skill not in found:
                found.append(CANONICAL.get(skill, skill))
    return found


def match_skills(job_skills: list[str], candidate_skills: list[str], title: str) -> SkillMatch:
    job_norm = [_norm(skill) for skill in job_skills]
    cand_norm = {_norm(skill) for skill in candidate_skills}
    matched = [skill for skill in job_skills if _norm(skill) in cand_norm]
    missing = [skill for skill in job_skills if _norm(skill) not in cand_norm]

    job_ecos = _ecosystems_for(job_norm)
    cand_ecos = _ecosystems_for(list(cand_norm))
    ecosystem_hits = sorted(job_ecos & cand_ecos)

    exact = len(matched) / max(len(job_skills), 1)
    partial = len(ecosystem_hits) / max(len(job_ecos), 1) if job_ecos else 0
    score = min(1.0, (0.7 * exact) + (0.3 * partial))
    if not job_skills:
        score = 0.45 if ecosystem_hits or cand_ecos else 0.2

    return SkillMatch(
        matched=matched,
        missing=missing,
        ecosystem_hits=ecosystem_hits,
        score=round(score, 3),
        resume_variant=_resume_variant(title, job_ecos),
        role_category=_role_category(title, job_ecos),
    )


def _contains_skill(text: str, skill: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(skill)}(?![a-z0-9])"
    return re.search(pattern, text, re.I) is not None


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _ecosystems_for(skills: list[str]) -> set[str]:
    hits: set[str] = set()
    normalized = {_norm(skill) for skill in skills}
    for name, members in ECOSYSTEMS.items():
        if any(_norm(member) in normalized for member in members):
            hits.add(name)
    return hits


def _role_category(title: str, ecosystems: set[str]) -> str:
    lowered = title.lower()
    if "frontend" in lowered or "front-end" in lowered:
        return RoleCategory.FRONTEND.value
    if "backend" in lowered or "back-end" in lowered:
        return RoleCategory.BACKEND.value
    if "full" in lowered and "stack" in lowered:
        return RoleCategory.FULL_STACK.value
    if "frontend" in ecosystems and "backend_js" in ecosystems:
        return RoleCategory.FULL_STACK.value
    if "frontend" in ecosystems:
        return RoleCategory.FRONTEND.value
    if "backend_js" in ecosystems:
        return RoleCategory.BACKEND.value
    return RoleCategory.UNKNOWN.value


def _resume_variant(title: str, ecosystems: set[str]) -> str:
    category = _role_category(title, ecosystems)
    if category == RoleCategory.FRONTEND.value:
        return ResumeVariant.SENIOR_FRONTEND_ENGINEER.value
    if category == RoleCategory.FULL_STACK.value:
        return ResumeVariant.FULL_STACK_ENGINEER.value
    return ResumeVariant.SENIOR_SOFTWARE_ENGINEER.value
