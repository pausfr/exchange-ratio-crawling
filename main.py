import os
import re
import time
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 사용할 통화 코드
CURRENCY = "USD"


class ExchangeRateCrawler:
    """환율 크롤링 및 저장 클래스"""

    def __init__(self):
        self.base_url = "https://www.kebhana.com/cont/mall/mall15/mall1501/index.jsp"
        self.driver = None
        self._setup_driver()

    def _setup_driver(self):
        """Selenium WebDriver 설정"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10)
            logger.info("Chrome WebDriver 초기화 완료")
        except Exception as e:
            logger.error(f"WebDriver 초기화 실패: {e}")
            self.driver = None

    def __del__(self):
        """소멸자 - WebDriver 종료"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

    def fetch_exchange_rates(self) -> List[Dict[str, Any]]:
        """KEB하나은행에서 환율 정보 크롤링 (Selenium 사용)"""
        if not self.driver:
            logger.error("WebDriver가 초기화되지 않았습니다")
            return []

        try:
            logger.info(f"환율 정보 크롤링 시작: {self.base_url}")

            print("=" * 50)
            print("메인 페이지 접속")
            print("=" * 50)

            self.driver.get(self.base_url)
            time.sleep(3)

            print(f"페이지 제목: {self.driver.title}")
            print(f"현재 URL: {self.driver.current_url}")

            # iframe으로 전환
            print("\n" + "=" * 50)
            print("iframe으로 전환")
            print("=" * 50)

            wait = WebDriverWait(self.driver, 10)
            iframe = wait.until(EC.presence_of_element_located((By.ID, "bankIframe")))
            self.driver.switch_to.frame('bankIframe')
            time.sleep(2)

            print("iframe 전환 완료")
            print(f"iframe 내 페이지 제목: {self.driver.title}")
            print(f"iframe 내 현재 URL: {self.driver.current_url}")

            # CURRENCY 선택 후 조회
            print("\n" + "=" * 50)
            print(f"{CURRENCY} 선택 및 조회")
            print("=" * 50)

            try:
                # CURRENCY 선택
                select = Select(self.driver.find_element(By.NAME, "curCd"))
                select.select_by_value(CURRENCY)
                time.sleep(1)

                # 최초 고시(라디오) 선택 (페이지 구조에 따라 XPATH가 달라질 수 있음)
                try:
                    first_rate_radio = self.driver.find_element(By.XPATH, '//*[@id="inqFrm"]/table/tbody/tr[3]/td/div/label[1]')
                    first_rate_radio.click()
                    time.sleep(2)
                except Exception:
                    # 실패해도 진행
                    pass

                # 페이지 소스 로드
                html = self.driver.page_source
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
            base_date: date = date.today()  # 기본값
            announcement_dt: Optional[datetime] = None  # 고시일시 (nullable)
            query_dt: Optional[datetime] = None  # 조회시각 (nullable)
            
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
                            # 고시일시 (날짜 strong + 시간 strong, 회차 strong은 무시)
                            em_ann = fl_span.find('em', string=lambda s: s and '고시일시' in s)
                            if em_ann:
                                strongs = []
                                for sib in em_ann.next_siblings:
                                    if getattr(sib, 'name', None) == 'strong':
                                        strongs.append(sib)
                                    if len(strongs) >= 3:  # 날짜, 시간, (회차)
                                        break
                                if strongs:
                                    ann_date = parse_date_kr(strongs[0].get_text())
                                    ann_time_tuple = parse_time_kr(strongs[1].get_text()) if len(strongs) > 1 else None
                                    if ann_date and ann_time_tuple:
                                        announcement_dt = datetime(ann_date.year, ann_date.month, ann_date.day,
                                                                   ann_time_tuple[0], ann_time_tuple[1], ann_time_tuple[2])
                        # 우측(span.fr): 조회시각 (한 strong에 날짜+시간)
                        fr_span = txt_rate_box.find('span', class_='fr')
                        if fr_span:
                            em_query = fr_span.find('em', string=lambda s: s and '조회시각' in s)
                            if em_query:
                                # em 다음 strong 하나에 전체 문자열
                                strong = None
                                for sib in em_query.next_siblings:
                                    if getattr(sib, 'name', None) == 'strong':
                                        strong = sib
                                        break
                                if strong:
                                    qdt = parse_datetime_full(strong.get_text())
                                    if qdt:
                                        query_dt = qdt
                            
                    else:
                        print("txtRateBox를 찾을 수 없어 오늘 날짜를 사용합니다.")
                else:
                    print("searchContentDiv를 찾을 수 없어 오늘 날짜를 사용합니다.")
            except Exception as e:
                print(f"날짜 파싱 중 오류 발생: {e}, 오늘 날짜를 사용합니다.")

            rate_table = soup.find('table', class_='tblBasic')

            if rate_table:
                tbody = rate_table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        # 테이블 구조가 바뀔 수 있으니 안전하게 길이 검사
                        if len(cells) >= 11:  # 실제 필요한 최대 인덱스 + 1
                            currency_cell = cells[0]
                            currency_link = currency_cell.find('a')
                            currency_text = currency_link.get_text().strip() if currency_link else currency_cell.get_text().strip()
                            if CURRENCY in currency_text:
                                print(f"{CURRENCY} 행 발견: {currency_text}")
                                # 안전한 float 파싱 함수
                                def parse_float_safe(cell) -> float:
                                    """안전한 float 파싱 - 빈값, None, 에러 시 0.0 반환"""
                                    if cell is None:
                                        return 0.0
                                    
                                    try:
                                        txt = cell.get_text().strip()
                                    except AttributeError:
                                        return 0.0
                                    
                                    # 빈값 또는 특수값 처리
                                    if not txt or txt in ['', '-', 'N/A', 'null', 'None', '0.00', '0']:
                                        return 0.0
                                    
                                    try:
                                        # 쉼표 제거 후 float 변환
                                        cleaned_txt = txt.replace(',', '').strip()
                                        return float(cleaned_txt)
                                    except (ValueError, AttributeError):
                                        return 0.0

                                # 각 필드별로 안전하게 파싱 (인덱스 기반)
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

                                # 환율 데이터 구성
                                rate_entry = {
                                    "base_date": base_date, # 기준일
                                    "currency_code": CURRENCY, # 통화코드
                                    "cash_buy": cash_buy, # 현찰 살 때 환율
                                    "cash_buy_spread": cash_buy_spread, # 현찰 살 때 환율 Spread
                                    "cash_sell": cash_sell, # 현찰 팔 때 환율
                                    "cash_sell_spread": cash_sell_spread, # 현찰 팔 때 환율 Spread
                                    "remit_send": remit_send, # 송금 보낼 때 환율
                                    "remit_receive": remit_receive, # 송금 받을 때 환율
                                    "check_sell": check_sell, # 외화 수표 팔 때 환율
                                    "rate": base_rate, # 매매기준율
                                    "exchange_fee_rate": exchange_fee_rate, # 환가료율
                                    "conversion_rate": conversion_rate, # 미화 환산율
                                    "announcement_datetime": announcement_dt, # 고시일시(datetime, nullable)
                                    "query_datetime": query_dt # 조회시각(datetime, nullable)
                                }

                                rates.append(rate_entry)
                                logger.info(f"{CURRENCY} 환율 데이터 파싱 완료")
                                print("  -> 파싱 완료:", rate_entry)
                                break
                else:
                    print("테이블에 tbody를 찾을 수 없습니다.")
            else:
                print("환율 테이블(tblBasic)을 찾을 수 없습니다.")

            print("\n" + "=" * 50)
            print("최종 크롤링 결과")
            print("=" * 50)
            for rate in rates:
                print(f"\n{rate['currency_code']} 환율 정보:")
                print(f"  기준일: {rate['base_date']}")
                print(f"  통화코드: {rate['currency_code']}")
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

            logger.info(f"크롤링 완료: {len(rates)}개 통화")
            return rates

        except Exception as e:
            logger.error(f"크롤링 중 오류 발생: {e}")
            return []
        finally:
            # iframe에서 나오기
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

    def run(self) -> bool:
        self.fetch_exchange_rates()
        return True


def main():
    """로컬 실행용 메인 함수"""
    crawler = ExchangeRateCrawler()
    success = crawler.run()
    if success:
        logger.info("로컬 실행 완료")


if __name__ == "__main__":
    main()
