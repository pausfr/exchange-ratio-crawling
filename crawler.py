import os
import re
import time
from datetime import date, datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 사용할 통화 코드
CURRENCY = "USD"
ANNOUNCEMENT_SEQUENCE = 1
ANNOUNCEMENT_TYPE = "FIRST"
BASE_URL = "https://www.kebhana.com/cont/mall/mall15/mall1501/index.jsp"


def handler(event=None, context=None):
    suc_cnt, err_cnt = crawler_target()
    return {
        "statusCode": 200,
        "suc_cnt": suc_cnt,
        "err_cnt": err_cnt
    }


def crawler_target():
    # Selenium 실행 옵션 설정 (Lambda 환경용)
    chrome_options = Options()
    chrome_options.binary_location = "/opt/chrome/chrome"
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("window-size=1392x1150")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"
    )

    # Lambda 전용 크롬 드라이버 경로 설정
    service = Service(executable_path="/opt/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    suc_cnt = 0
    err_cnt = 0

    # 크롤링 로직 구현
    try:
        print(f"환율 정보 크롤링 시작: {BASE_URL}")

        print("=" * 50)
        print("메인 페이지 접속")
        print("=" * 50)

        driver.get(BASE_URL)
        time.sleep(3)

        print(f"페이지 제목: {driver.title}")
        print(f"현재 URL: {driver.current_url}")

        # iframe으로 전환
        print("\n" + "=" * 50)
        print("iframe으로 전환")
        print("=" * 50)

        wait = WebDriverWait(driver, 10)
        iframe = wait.until(EC.presence_of_element_located((By.ID, "bankIframe")))
        driver.switch_to.frame('bankIframe')
        time.sleep(2)

        print("iframe 전환 완료")
        print(f"iframe 내 페이지 제목: {driver.title}")
        print(f"iframe 내 현재 URL: {driver.current_url}")

        # CURRENCY 선택 후 조회
        print("\n" + "=" * 50)
        print(f"{CURRENCY} 선택 및 조회")
        print("=" * 50)

        try:
            # CURRENCY 선택
            select = Select(driver.find_element(By.NAME, "curCd"))
            select.select_by_value(CURRENCY)
            time.sleep(1)

            # 최초 고시(라디오) 선택
            try:
                first_rate_radio = driver.find_element(By.XPATH, '//*[@id="inqFrm"]/table/tbody/tr[3]/td/div/label[1]')
                first_rate_radio.click()
                time.sleep(2)
            except Exception:
                pass

            # 페이지 소스 로드
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

        except Exception as e:
            print(f"{CURRENCY} 조회 중 오류 발생: {e}")

        # 환율 데이터 파싱
        print("\n" + "=" * 50)
        print("실제 환율 데이터 파싱 (HTML 구조 기반)")
        print("=" * 50)

        rates: List[Dict[str, Any]] = []

        # Helper parsers for KR date/time strings
        def parse_date_kr(text: str) -> Optional[date]:
            m = re.search(r'(\d{4})년\s*(\d{2})월\s*(\d{2})일', text)
            if not m:
                return None
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        def parse_time_kr(text: str) -> Optional[tuple]:
            m = re.search(r'(\d{2})시\s*(\d{2})분\s*(\d{2})초', text)
            if not m:
                return None
            return int(m.group(1)), int(m.group(2)), int(m.group(3))

        def parse_datetime_full(text: str) -> Optional[datetime]:
            d = parse_date_kr(text)
            t = parse_time_kr(text)
            if d and t:
                return datetime(d.year, d.month, d.day, t[0], t[1], t[2])
            return None

        # 실제 기준일, 고시일시, 조회시각 파싱
        base_date: date = date.today()
        announcement_dt: Optional[datetime] = None
        query_dt: Optional[datetime] = None
        
        try:
            search_content_div = soup.find('div', id='searchContentDiv')
            if search_content_div:
                txt_rate_box = search_content_div.find('p', class_='txtRateBox')
                if txt_rate_box:
                    # 좌측(span.fl): 기준일, 고시일시
                    fl_span = txt_rate_box.find('span', class_='fl')
                    if fl_span:
                        # 기준일
                        em_base = fl_span.find('em', string=lambda s: s and '기준일' in s)
                        if em_base:
                            strongs = []
                            for sib in em_base.next_siblings:
                                if getattr(sib, 'name', None) == 'strong':
                                    strongs.append(sib)
                                if len(strongs) >= 1:
                                    break
                            if strongs:
                                bd = parse_date_kr(strongs[0].get_text())
                                if bd:
                                    base_date = bd
                        # 고시일시
                        em_ann = fl_span.find('em', string=lambda s: s and '고시일시' in s)
                        if em_ann:
                            strongs = []
                            for sib in em_ann.next_siblings:
                                if getattr(sib, 'name', None) == 'strong':
                                    strongs.append(sib)
                                if len(strongs) >= 3:
                                    break
                            if strongs:
                                ann_date = parse_date_kr(strongs[0].get_text())
                                ann_time_tuple = parse_time_kr(strongs[1].get_text()) if len(strongs) > 1 else None
                                if ann_date and ann_time_tuple:
                                    announcement_dt = datetime(ann_date.year, ann_date.month, ann_date.day,
                                                               ann_time_tuple[0], ann_time_tuple[1], ann_time_tuple[2])
                    # 우측(span.fr): 조회시각
                    fr_span = txt_rate_box.find('span', class_='fr')
                    if fr_span:
                        em_query = fr_span.find('em', string=lambda s: s and '조회시각' in s)
                        if em_query:
                            strong = None
                            for sib in em_query.next_siblings:
                                if getattr(sib, 'name', None) == 'strong':
                                    strong = sib
                                    break
                            if strong:
                                qdt = parse_datetime_full(strong.get_text())
                                if qdt:
                                    query_dt = qdt
        except Exception as e:
            print(f"날짜 파싱 중 오류 발생: {e}, 오늘 날짜를 사용합니다.")

        rate_table = soup.find('table', class_='tblBasic')

        if rate_table:
            tbody = rate_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 11:
                        currency_cell = cells[0]
                        currency_link = currency_cell.find('a')
                        currency_text = currency_link.get_text().strip() if currency_link else currency_cell.get_text().strip()
                        if CURRENCY in currency_text:
                            print(f"{CURRENCY} 행 발견: {currency_text}")
                            
                            def parse_float_safe(cell) -> float:
                                if cell is None:
                                    return 0.0
                                try:
                                    txt = cell.get_text().strip()
                                except AttributeError:
                                    return 0.0
                                if not txt or txt in ['', '-', 'N/A', 'null', 'None', '0.00', '0']:
                                    return 0.0
                                try:
                                    cleaned_txt = txt.replace(',', '').strip()
                                    return float(cleaned_txt)
                                except (ValueError, AttributeError):
                                    return 0.0

                            cash_buy = parse_float_safe(cells[1])
                            cash_buy_spread = parse_float_safe(cells[2])
                            cash_sell = parse_float_safe(cells[3])
                            cash_sell_spread = parse_float_safe(cells[4])
                            remit_send = parse_float_safe(cells[5])
                            remit_receive = parse_float_safe(cells[6])
                            check_sell = parse_float_safe(cells[7])
                            base_rate = parse_float_safe(cells[8])
                            exchange_fee_rate = parse_float_safe(cells[9])
                            conversion_rate = parse_float_safe(cells[10])

                            rate_entry = {
                                "base_date": base_date,
                                "currency_code": CURRENCY,
                                "announcement_sequence": ANNOUNCEMENT_SEQUENCE,
                                "announcement_type": ANNOUNCEMENT_TYPE,
                                "cash_buy": cash_buy,
                                "cash_buy_spread": cash_buy_spread,
                                "cash_sell": cash_sell,
                                "cash_sell_spread": cash_sell_spread,
                                "remit_send": remit_send,
                                "remit_receive": remit_receive,
                                "check_sell": check_sell,
                                "rate": base_rate,
                                "exchange_fee_rate": exchange_fee_rate,
                                "conversion_rate": conversion_rate,
                                "announcement_datetime": announcement_dt,
                                "query_datetime": query_dt
                            }

                            rates.append(rate_entry)
                            print("  -> 파싱 완료:", rate_entry)
                            break

        print("\n" + "=" * 50)
        print("최종 크롤링 결과")
        print("=" * 50)
        for rate in rates:
            print(f"\n{rate['currency_code']} 환율 정보:")
            print(f"  기준일: {rate['base_date']}")
            print(f"  통화코드: {rate['currency_code']}")
            print(f"  고시차수: {rate['announcement_sequence']}")
            print(f"  고시유형: {rate['announcement_type']}")
            print(f"  현찰 살 때 환율: {rate['cash_buy']} (Spread: {rate['cash_buy_spread']})")
            print(f"  현찰 팔 때 환율: {rate['cash_sell']} (Spread: {rate['cash_sell_spread']})")
            print(f"  송금 보낼 때 환율: {rate['remit_send']}")
            print(f"  송금 받을 때 환율: {rate['remit_receive']}")
            print(f"  외화 수표 팔 때 환율: {rate['check_sell']}")
            print(f"  매매기준율: {rate['rate']}")
            print(f"  환가료율: {rate['exchange_fee_rate']}")
            print(f"  미화 환산율: {rate['conversion_rate']}")
            print(f"  고시일시: {rate['announcement_datetime']}")
            print(f"  조회시각: {rate['query_datetime']}")

        # iframe에서 나오기
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        # 성공 카운트 증가
        suc_cnt += 1
        print(f"크롤링 성공! 성공 건수: {suc_cnt}")
        
    except Exception as e:
        print(f"크롤링 중 오류 발생: {str(e)}")
        err_cnt += 1
        
    # 크롤링 로직 구현 완료 
    
    driver.quit()
    return suc_cnt, err_cnt