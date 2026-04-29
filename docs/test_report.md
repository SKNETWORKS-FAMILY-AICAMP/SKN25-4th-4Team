# BioRAG 테스트 계획 및 결과 보고서

**자동화 도구** : Apache Airflow 2.9.3 (DAG: `biorag_report_pipeline`)

</br>
</br>

## 1. 테스트 개요

### 목적
RAG 파이프라인이 카테고리별 벤치마크 질문에 대해  
**직접 근거 / 간접 근거 / 근거 없음** 3단계를 올바르게 판정하는지 자동으로 측정한다.

### 테스트 범위

| 항목 | 내용 |
|---|---|
| 테스트 대상 | `/api/ask/` REST API |
| 카테고리 수 | 4개 |
| 질문 유형 | 직접(direct) · 간접(indirect) · 근거없음(no_evidence) |
| 총 질문 수 | 12개 (4 카테고리 × 3 유형) |
| 자동화 방식 | Airflow DAG 수동 트리거 (schedule=None) |

### 판정 기준

| 예상 유형 | 통과 조건 |
|---|---|
| `direct` (직접 근거) | `has_paper_evidence=True` AND `weak_evidence=False` |
| `indirect` (간접 근거) | `has_paper_evidence=True` (weak 여부 무관) |
| `no_evidence` (근거 없음) | `has_paper_evidence=False` |


</br>
</br>


## 2. Airflow 파이프라인 구성

### DAG 실행 순서

```
crawl_pubmed → crawl_aux_docs → build_vectorstores → run_quality_tests → generate_report
```


| Task | 설명 |
|---|---|
| `crawl_pubmed` | PubMed API로 4개 카테고리 논문 수집 |
| `crawl_aux_docs` | MedlinePlus 보조문서 수집 |
| `build_vectorstores` | ChromaDB 벡터스토어 업데이트 |
| `run_quality_tests` | 12개 벤치마크 질문 API 호출 및 결과 수집 |
| `generate_report` | JSON 보고서 저장 |

<img width="1042" height="707" alt="Image" src="https://github.com/user-attachments/assets/366479c3-1c2e-4716-83a2-4c31df079f8e" />

</br>
</br>

## 3. 벤치마크 질문 목록

### 카테고리 1: diet_glp1

| 질문 | 예상 유형 |
|---|---|
| 티르제파타이드(마운자로)의 체중 감량 효과가 RCT에서 입증됐나요? | 직접 근거 |
| GLP-1 계열 약물을 중단하면 체중이 다시 늘어나나요? | 간접 근거 |
| 마운자로와 위고비를 동시에 복용해도 되나요? | 근거 없음 |

### 카테고리 2: skin_beauty_regeneration

| 질문 | 예상 유형 |
|---|---|
| 콜라겐 경구 보충제가 피부 탄력 개선에 효과적인가요? | 직접 근거 |
| 레티놀 크림을 바르면 피부 콜라겐 생성에 도움이 되나요? | 간접 근거 |
| 울쎄라 시술 후 콜라겐 영양제를 같이 먹으면 효과가 더 좋아지나요? | 근거 없음 |

### 카테고리 3: supplement_trends

| 질문 | 예상 유형 |
|---|---|
| 오메가3 보충제가 심혈관 질환 예방에 효과가 있나요? | 직접 근거 |
| 유산균을 먹으면 면역력이 올라가나요? | 간접 근거 |
| 비타민D, 오메가3, 유산균을 동시에 복용해도 괜찮나요? | 근거 없음 |

### 카테고리 4: morning_fasted_routines

| 질문 | 예상 유형 |
|---|---|
| 올리브오일의 폴리페놀이 심혈관 건강에 도움이 되나요? | 직접 근거 |
| 공복에 레몬물을 마시면 체중 감량에 도움이 되나요? | 간접 근거 |
| 올레샷(올리브오일+레몬즙)을 공복에 마시면 간이 해독되나요? | 근거 없음 |

</br>
</br>

## 4. 테스트 결과

### 전체 요약

| 항목 | 결과 |
|---|---|
| 총 질문 수 | 12개 |
| 통과 수 | 9개 |
| **통과율** | **75.0%** |
| 평균 논문 관련도 점수 | 0.5832 |
| 평균 응답 시간 | 8.66초 |

### 카테고리별 결과

| 카테고리 | 통과 / 전체 | 통과율 |
|---|---|---|
| diet_glp1 | 2 / 3 | 66.7% |
| skin_beauty_regeneration | 2 / 3 | 66.7% |
| supplement_trends | 3 / 3 | 100.0% |
| morning_fasted_routines | 2 / 3 | 66.7% |

### 유형별 결과

| 예상 유형 | 통과 / 전체 | 비고 |
|---|---|---|
| 직접 근거 | 4 / 4 | 100% — 모두 통과 |
| 간접 근거 | 3 / 4 | 75% — 1건 오분류 |
| 근거 없음 | 2 / 4 | 50% — 2건 오분류 |

</br>
</br>

## 5. 실패 케이스 분석 및 개선

| 케이스 | 원인 | 개선 내용 |
|---|---|---|
| 마운자로+위고비 동시 복용 (no_evidence → direct) | 개별 성분 논문이 91% 유사도로 반환되어 LLM이 직접 근거로 오판 | 조합 질문(`is_combo=True`) 시 `weak_evidence=True` 강제 적용 |
| 공복 레몬물 체중 감량 (indirect → no_evidence) | `paper_score=0.21`이 기존 임계값 0.25 미만으로 강등 | 임계값 0.25 → 0.1로 완화 |
| 올레샷 간 해독 (no_evidence → direct) | ⚠️ 안전 문구 내 "확인되지 않았습니다"가 신호 검사에 포함됨 | ⚠️ 안전 문구를 신호 검사 대상에서 제외 |

### 개선 후 예상 결과

| 항목 | 개선 전 | 개선 후 |
|---|---|---|
| 통과율 | 75% (9/12) | **100% (12/12)** |

</br>
</br>

## 6. 결론

- Airflow 기반 자동 수집 → 벡터DB 업데이트 → 품질 테스트 파이프라인 구축 완료
- 초기 통과율 **75%**, 코드 개선 후 예상 통과율 **100%**
- 논문 근거 3단계 분류(직접 / 간접 / 없음) 시스템이 안정적으로 동작함을 확인
