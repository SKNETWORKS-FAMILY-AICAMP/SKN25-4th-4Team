"""
BioRAG 데이터 수집 크롤러
- PubMed API로 논문 수집
- 건강 트렌드 용어사전 생성
- 건강 뉴스 RSS 수집 (선택)
"""

import time
import json
import os
import requests
from xml.etree import ElementTree as ET
from datetime import datetime


# 1. PubMed 논문 수집 설정

# 수집할 키워드 목록 (15개)
KEYWORDS = [
    "GLP-1 receptor agonist weight loss tirzepatide",      # 마운자로
    "intermittent fasting metabolic syndrome",              # 간헐적 단식
    "omega-3 fatty acids cardiovascular disease",           # 오메가3
    "ketogenic diet diabetes weight loss",                  # 저탄고지
    "statin side effects cardiovascular",                   # 콜레스테롤약
    "probiotic gut microbiome health",                      # 프로바이오틱스
    "apple polyphenol antioxidant health",                  # 사과 효능
    "olive oil cardiovascular polyphenol",                  # 올리브유
    "lemon vitamin C immune system",                        # 레몬
    "metformin diabetes prevention aging",                  # 메트포르민
    "vitamin D deficiency depression",                      # 비타민D
    "caffeine cognitive performance alertness",             # 카페인
    "sleep deprivation immune system health",               # 수면
    "aspirin cardiovascular prevention risk",               # 아스피린
    "green tea catechin metabolism weight",                 # 녹차
]

# PubMed API 기본 URL
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"



# 2. 건강 트렌드 용어사전

KOREAN_HEALTH_GLOSSARY = [
    {
        "term": "올레샷",
        "definition": "올리브유 + 레몬즙을 섞어 아침 공복에 마시는 건강법",
        "keywords": ["olive oil polyphenol", "lemon vitamin C", "morning fasting", "cardiovascular health"],
        "category": "식이요법"
    },
    {
        "term": "저탄고지",
        "definition": "저탄수화물 고지방 식이요법 (케토제닉 다이어트)",
        "keywords": ["ketogenic diet", "low carb high fat", "LCHF", "weight loss"],
        "category": "식이요법"
    },
    {
        "term": "마운자로",
        "definition": "티르제파타이드(Tirzepatide) 성분의 당뇨병 및 비만 치료제",
        "keywords": ["tirzepatide", "GLP-1 receptor agonist", "weight loss medication", "diabetes"],
        "category": "의약품"
    },
    {
        "term": "애사비",
        "definition": "아침(아) + 사과(사) + 비타민(비) - 아침 공복에 사과와 비타민 섭취",
        "keywords": ["apple fasting", "morning fruit", "pectin fiber", "vitamin supplement"],
        "category": "식이요법"
    },
    {
        "term": "간헐적단식",
        "definition": "일정 시간 공복을 유지한 후 식사하는 방법 (16:8, 5:2 등)",
        "keywords": ["intermittent fasting", "time-restricted eating", "16:8 fasting", "metabolic health"],
        "category": "식이요법"
    },
    {
        "term": "오메가3",
        "definition": "EPA, DHA 등 불포화지방산 함유 건강보조식품",
        "keywords": ["omega-3 fatty acids", "EPA DHA", "fish oil", "cardiovascular"],
        "category": "건강보조식품"
    },
    {
        "term": "프로바이오틱스",
        "definition": "장 건강에 도움을 주는 유익균 (락토바실러스, 비피더스균 등)",
        "keywords": ["probiotics", "gut microbiome", "lactobacillus", "digestive health"],
        "category": "건강보조식품"
    },
    {
        "term": "콜레스테롤약",
        "definition": "스타틴 계열 고지혈증 치료제 (아토르바스타틴 등)",
        "keywords": ["statin", "atorvastatin", "cholesterol medication", "cardiovascular"],
        "category": "의약품"
    },
    {
        "term": "메트포르민",
        "definition": "2형 당뇨병 1차 치료제로 사용되는 약물",
        "keywords": ["metformin", "diabetes medication", "blood sugar control", "anti-aging"],
        "category": "의약품"
    },
    {
        "term": "비타민D",
        "definition": "뼈 건강, 면역력, 기분 조절에 관여하는 지용성 비타민",
        "keywords": ["vitamin D", "cholecalciferol", "bone health", "immune system", "depression"],
        "category": "건강보조식품"
    },
    {
        "term": "칼로리제로",
        "definition": "열량이 없거나 극히 낮은 식품 또는 음료",
        "keywords": ["zero calorie", "artificial sweetener", "diet beverage", "aspartame"],
        "category": "식품"
    },
    {
        "term": "단백질보충제",
        "definition": "근육 성장과 회복을 위한 단백질 파우더 (유청, 대두 등)",
        "keywords": ["protein supplement", "whey protein", "muscle building", "workout recovery"],
        "category": "건강보조식품"
    },
    {
        "term": "디톡스",
        "definition": "체내 독소 배출을 목적으로 하는 식이요법 또는 요법",
        "keywords": ["detox", "cleanse", "toxin removal", "juice cleanse"],
        "category": "식이요법"
    },
    {
        "term": "글루텐프리",
        "definition": "밀, 보리 등의 글루텐 단백질을 제거한 식단",
        "keywords": ["gluten free", "celiac disease", "wheat allergy", "gut health"],
        "category": "식이요법"
    },
    {
        "term": "락토프리",
        "definition": "유당(락토스)을 제거한 유제품",
        "keywords": ["lactose free", "dairy intolerance", "lactase deficiency"],
        "category": "식품"
    },
]



# 3. PubMed 논문 수집 함수

def search_pubmed_ids(keyword, max_results=30):
    """
    키워드로 PubMed 논문 ID(PMID) 검색
    """
    url = f"{PUBMED_BASE}/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": keyword,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
        "usehistory": "y"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        pmids = data.get("esearchresult", {}).get("idlist", [])
        count = data.get("esearchresult", {}).get("count", "0")
        
        print(f"  '{keyword}' → {len(pmids)}개 논문 ID 검색됨 (전체: {count}개)")
        return pmids
    
    except Exception as e:
        print(f" 검색 실패: {e}")
        return []


def fetch_pubmed_abstracts(pmid_list):
    """
    PMID 목록으로 논문 상세 정보(초록 포함) 가져오기
    """
    if not pmid_list:
        return []
    
    url = f"{PUBMED_BASE}/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pmid_list),
        "rettype": "abstract",
        "retmode": "xml"
    }
    
    try:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        return response.text
    
    except Exception as e:
        print(f" 논문 가져오기 실패: {e}")
        return ""


def parse_pubmed_xml(xml_text, keyword):
    """
    PubMed XML 파싱하여 논문 정보 추출
    """
    if not xml_text:
        return []
    
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f" XML 파싱 실패: {e}")
        return []
    
    papers = []
    
    for article in root.findall(".//PubmedArticle"):
        try:
            # 기본 정보
            pmid = article.findtext(".//PMID", default="")
            title = article.findtext(".//ArticleTitle", default="")
            
            # 초록 (여러 섹션으로 나뉠 수 있음)
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join(
                (part.text or "") for part in abstract_parts
            ).strip()
            
            # 저널 정보
            journal = article.findtext(".//Journal/Title", default="")
            iso_abbr = article.findtext(".//Journal/ISOAbbreviation", default="")
            
            # 발행 연도
            year = article.findtext(".//PubDate/Year", default="")
            if not year:
                year = article.findtext(".//PubDate/MedlineDate", default="")[:4]
            
            # 저자 (첫 번째 저자만)
            first_author = article.findtext(".//Author/LastName", default="")
            
            # DOI
            doi = ""
            for article_id in article.findall(".//ArticleId"):
                if article_id.get("IdType") == "doi":
                    doi = article_id.text or ""
                    break
            
            # 초록이 없는 논문은 제외
            if not abstract or len(abstract) < 100:
                continue
            
            # 논문 정보 저장
            paper = {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal or iso_abbr,
                "year": year,
                "first_author": first_author,
                "doi": doi,
                "keyword": keyword,
                "source": f"{journal or iso_abbr} ({year}) PMID:{pmid}",
                "collected_at": datetime.now().isoformat()
            }
            
            papers.append(paper)
        
        except Exception as e:
            print(f" 논문 파싱 중 오류: {e}")
            continue
    
    return papers


def collect_pubmed_papers(keywords, max_per_keyword=30):
    """
    전체 키워드에 대해 PubMed 논문 수집
    """
    print(" PubMed 논문 수집 시작")
    
    all_papers = []
    
    for i, keyword in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}] 수집 중: {keyword}")
        
        # 1단계: PMID 검색
        pmids = search_pubmed_ids(keyword, max_per_keyword)
        
        if not pmids:
            print(f" 검색 결과 없음, 다음 키워드로 이동\n")
            continue
        
        # 2단계: 논문 상세 정보 가져오기
        xml_data = fetch_pubmed_abstracts(pmids)
        
        # 3단계: XML 파싱
        papers = parse_pubmed_xml(xml_data, keyword)
        
        print(f"  {len(papers)}개 논문 수집 완료\n")
        all_papers.extend(papers)
        
        # API 제한 준수 (0.4초 대기)
        time.sleep(0.4)
    
    # 중복 PMID 제거
    seen_pmids = set()
    unique_papers = []
    for paper in all_papers:
        if paper["pmid"] not in seen_pmids:
            seen_pmids.add(paper["pmid"])
            unique_papers.append(paper)
    
    print(f" 총 {len(unique_papers)}개 고유 논문 수집 완료")
    
    return unique_papers



# 4. 용어사전 저장

def save_glossary():
    """
    건강 트렌드 용어사전 JSON 저장
    """
    print(" 건강 트렌드 용어사전 생성")
    
    # 각 용어에 메타데이터 추가
    for term_data in KOREAN_HEALTH_GLOSSARY:
        term_data["source"] = "glossary"
        term_data["collected_at"] = datetime.now().isoformat()
    
    os.makedirs("data/raw", exist_ok=True)
    
    with open("data/raw/glossary.json", "w", encoding="utf-8") as f:
        json.dump(KOREAN_HEALTH_GLOSSARY, f, ensure_ascii=False, indent=2)
    
    print(f" {len(KOREAN_HEALTH_GLOSSARY)}개 용어 저장 완료")
    print(f"   파일 위치: data/raw/glossary.json\n")



# 5. 메인 실행 함수

def main():
    """
    전체 데이터 수집 파이프라인 실행
    """
    print("BioRAG 데이터 수집 시작")
    
    start_time = time.time()
    
    # 1. 출력 폴더 생성
    os.makedirs("data/raw", exist_ok=True)
    
    # 2. PubMed 논문 수집
    papers = collect_pubmed_papers(KEYWORDS, max_per_keyword=30)
    
    # 3. 논문 데이터 저장
    if papers:
        with open("data/raw/papers.json", "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"논문 데이터 저장: data/raw/papers.json\n")
    
    # 4. 용어사전 저장
    save_glossary()
    
    # 5. 완료 메시지
    elapsed = time.time() - start_time

    print(f" 전체 수집 완료 (소요 시간: {elapsed:.1f}초)")
    print("\n 수집 결과:")
    print(f"   - 논문: {len(papers)}개")
    print(f"   - 용어사전: {len(KOREAN_HEALTH_GLOSSARY)}개")
    print("\n 저장 위치:")
    print(f"   - data/raw/papers.json")
    print(f"   - data/raw/glossary.json")
    print("\n 다음 단계: python pipeline/preprocess.py\n")


if __name__ == "__main__":
    main()