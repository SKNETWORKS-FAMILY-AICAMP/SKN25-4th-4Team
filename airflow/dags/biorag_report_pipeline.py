"""
BioRAG 데이터 수집 + 품질 테스트 파이프라인 DAG.

schedule=None → Airflow UI에서 수동으로 한 번 실행.
실행 순서:
  1. crawl_pubmed      — PubMed 논문 수집
  2. crawl_aux_docs    — MedlinePlus 보조문서 수집  (1과 병렬)
  3. build_vectorstores — ChromaDB 업데이트
  4. run_quality_tests  — 카테고리별 벤치마크 질문으로 RAG 성능 측정
  5. generate_report    — JSON 보고서 저장
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

# 카테고리별 벤치마크 질문 (4개 카테고리 × 3종류 = 12개)
# expected_type:
#   direct      → 논문 직접 근거 예상 (has_paper_evidence=True, weak_evidence=False)
#   indirect    → 간접 근거 예상      (has_paper_evidence=True, weak_evidence=True)
#   no_evidence → 근거 없음 예상      (has_paper_evidence=False)
BENCHMARK_QUESTIONS = [
    # ── diet_glp1 ──
    {
        "question": "티르제파타이드(마운자로)의 체중 감량 효과가 RCT에서 입증됐나요?",
        "category": "diet_glp1",
        "expected_type": "direct",
    },
    {
        "question": "GLP-1 계열 약물을 중단하면 체중이 다시 늘어나나요?",
        "category": "diet_glp1",
        "expected_type": "indirect",
    },
    {
        "question": "마운자로와 위고비를 동시에 복용해도 되나요?",
        "category": "diet_glp1",
        "expected_type": "no_evidence",
    },

    # ── skin_beauty_regeneration ──
    {
        "question": "콜라겐 경구 보충제가 피부 탄력 개선에 효과적인가요?",
        "category": "skin_beauty_regeneration",
        "expected_type": "direct",
    },
    {
        "question": "레티놀 크림을 바르면 피부 콜라겐 생성에 도움이 되나요?",
        "category": "skin_beauty_regeneration",
        "expected_type": "indirect",
    },
    {
        "question": "울쎄라 시술 후 콜라겐 영양제를 같이 먹으면 효과가 더 좋아지나요?",
        "category": "skin_beauty_regeneration",
        "expected_type": "no_evidence",
    },

    # ── supplement_trends ──
    {
        "question": "오메가3 보충제가 심혈관 질환 예방에 효과가 있나요?",
        "category": "supplement_trends",
        "expected_type": "direct",
    },
    {
        "question": "유산균을 먹으면 면역력이 올라가나요?",
        "category": "supplement_trends",
        "expected_type": "indirect",
    },
    {
        "question": "비타민D, 오메가3, 유산균을 동시에 복용해도 괜찮나요?",
        "category": "supplement_trends",
        "expected_type": "no_evidence",
    },

    # ── morning_fasted_routines ──
    {
        "question": "올리브오일의 폴리페놀이 심혈관 건강에 도움이 되나요?",
        "category": "morning_fasted_routines",
        "expected_type": "direct",
    },
    {
        "question": "공복에 레몬물을 마시면 체중 감량에 도움이 되나요?",
        "category": "morning_fasted_routines",
        "expected_type": "indirect",
    },
    {
        "question": "올레샷(올리브오일+레몬즙)을 공복에 마시면 간이 해독되나요?",
        "category": "morning_fasted_routines",
        "expected_type": "no_evidence",
    },
]

FASTAPI_URL = "http://fastapi:8000"
REPORT_DIR = Path("/opt/biorag/data/reports")

default_args = {
    "owner": "biorag",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}


# ── Task 함수 ──────────────────────────────────────────────────────────────


def task_crawl_pubmed(**context):
    import sys
    sys.path.insert(0, "/opt/biorag")
    from dotenv import load_dotenv
    load_dotenv("/opt/biorag/.env")

    from ingestion.crawl_pubmed import crawl_pubmed
    output = crawl_pubmed()
    print(f"PubMed 수집 완료: {output}")
    return str(output)


def task_crawl_aux_docs(**context):
    import sys
    sys.path.insert(0, "/opt/biorag")
    from dotenv import load_dotenv
    load_dotenv("/opt/biorag/.env")

    from ingestion.crawl_aux_docs import crawl_aux_docs
    output = crawl_aux_docs()
    print(f"보조문서 수집 완료: {output}")
    return str(output)


def task_build_vectorstores(**context):
    import sys
    sys.path.insert(0, "/opt/biorag")
    from dotenv import load_dotenv
    load_dotenv("/opt/biorag/.env")

    from ingestion.build_vectorstores import build_vectorstores
    build_vectorstores(reset=False)
    print("벡터스토어 업데이트 완료")


def task_run_quality_tests(**context):
    import requests

    results = []
    for item in BENCHMARK_QUESTIONS:
        question = item["question"]
        start = time.time()
        try:
            resp = requests.post(
                f"{FASTAPI_URL}/api/ask",
                json={"question": question},
                timeout=90,
            )
            elapsed = round(time.time() - start, 2)
            data = resp.json()
            has_evidence = data.get("has_paper_evidence", False)
            weak = data.get("weak_evidence", False)
            expected = item["expected_type"]

            # 예상 결과와 실제 결과 비교
            if expected == "direct":
                passed = has_evidence and not weak
            elif expected == "indirect":
                passed = has_evidence  # weak 여부는 무관하게 근거가 있으면 통과
            else:  # no_evidence
                passed = not has_evidence

            results.append({
                "question": question,
                "category": item["category"],
                "expected_type": expected,
                "has_paper_evidence": has_evidence,
                "weak_evidence": weak,
                "paper_score": round(data.get("paper_score", 0.0), 4),
                "paper_sources_count": len(data.get("paper_sources", [])),
                "response_time_s": elapsed,
                "answer_preview": data.get("answer", "")[:120],
                "pass": passed,
                "status": "ok",
            })
            result_icon = "✓" if passed else "✗"
            print(f"[{result_icon}] {question[:40]}... | {expected} | score={data.get('paper_score', 0):.3f} | {elapsed}s")
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            results.append({
                "question": question,
                "category": item["category"],
                "status": "error",
                "error": str(e),
                "response_time_s": elapsed,
            })
            print(f"[ERR] {question[:40]}... | {e}")
        time.sleep(2)  # API 과부하 방지

    context["ti"].xcom_push(key="test_results", value=results)
    return results


def task_generate_report(**context):
    ti = context["ti"]
    results = ti.xcom_pull(task_ids="run_quality_tests", key="test_results") or []

    ok = [r for r in results if r.get("status") == "ok"]
    pass_count = sum(1 for r in ok if r.get("pass"))
    evidence_count = sum(1 for r in ok if r.get("has_paper_evidence"))
    avg_score = sum(r.get("paper_score", 0) for r in ok) / len(ok) if ok else 0
    avg_time = sum(r.get("response_time_s", 0) for r in results) / len(results) if results else 0

    report = {
        "generated_at": datetime.now().isoformat(),
        "pipeline": {
            "crawl_pubmed": "completed",
            "crawl_aux_docs": "completed",
            "build_vectorstores": "completed",
        },
        "summary": {
            "total_questions": len(BENCHMARK_QUESTIONS),
            "ok_count": len(ok),
            "error_count": len(results) - len(ok),
            "pass_count": pass_count,
            "pass_rate_pct": round(pass_count / len(ok) * 100, 1) if ok else 0,
            "evidence_rate_pct": round(evidence_count / len(ok) * 100, 1) if ok else 0,
            "avg_paper_score": round(avg_score, 4),
            "avg_response_time_s": round(avg_time, 2),
        },
        "by_category": {},
        "results": results,
    }

    # 카테고리별 집계
    for cat in {r["category"] for r in ok}:
        cat_results = [r for r in ok if r["category"] == cat]
        report["by_category"][cat] = {
            "count": len(cat_results),
            "evidence_rate_pct": round(
                sum(1 for r in cat_results if r.get("has_paper_evidence")) / len(cat_results) * 100, 1
            ),
            "avg_score": round(sum(r.get("paper_score", 0) for r in cat_results) / len(cat_results), 4),
        }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"quality_report_{ts}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n========== BioRAG 품질 보고서 ==========")
    print(f"총 질문: {report['summary']['total_questions']}개 (카테고리 4 × 유형 3)")
    print(f"테스트 통과: {pass_count}/{len(ok)}개 ({report['summary']['pass_rate_pct']}%)")
    print(f"논문 근거 있음: {evidence_count}/{len(ok)}개 ({report['summary']['evidence_rate_pct']}%)")
    print(f"평균 관련도 점수: {report['summary']['avg_paper_score']:.4f}")
    print(f"평균 응답 시간: {report['summary']['avg_response_time_s']}초")
    print(f"보고서 저장: {report_path}")
    print("=========================================")

    return str(report_path)


# ── DAG 정의 ───────────────────────────────────────────────────────────────

with DAG(
    dag_id="biorag_report_pipeline",
    default_args=default_args,
    description="BioRAG 데이터 수집 → 벡터DB 업데이트 → 품질 테스트 보고서 (수동 1회 실행)",
    schedule=None,          # UI에서 수동 트리거
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["biorag", "ingestion", "report"],
) as dag:

    crawl_pubmed = PythonOperator(
        task_id="crawl_pubmed",
        python_callable=task_crawl_pubmed,
    )

    crawl_aux_docs = PythonOperator(
        task_id="crawl_aux_docs",
        python_callable=task_crawl_aux_docs,
    )

    build_vectorstores = PythonOperator(
        task_id="build_vectorstores",
        python_callable=task_build_vectorstores,
    )

    run_quality_tests = PythonOperator(
        task_id="run_quality_tests",
        python_callable=task_run_quality_tests,
    )

    generate_report = PythonOperator(
        task_id="generate_report",
        python_callable=task_generate_report,
    )

    # SequentialExecutor: 순차 실행
    crawl_pubmed >> crawl_aux_docs >> build_vectorstores >> run_quality_tests >> generate_report
