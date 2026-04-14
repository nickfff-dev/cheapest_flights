import requests
from dotenv import load_dotenv
import os


load_dotenv()
http_proxy = os.environ.get('http_proxy', 'No proxy')


def fetch_flights(url):
    cookies = {
    '__Secure-BUCKET': 'CCQ',
    'OTZ': '8543161_44_44__44_',
    'SID': 'g.a0008gjhPfbzH1FITb7Hj_yG16Nl3RSTFH7RGujeHAdpqj8-mwn5dRWSJfciB4Z8Aps_nQ2Q1QACgYKAUUSARASFQHGX2Mi521OXrfIe2EYwt6uWC-Z-xoVAUF8yKrnNLARJYVI0JWDWQc4OTCk0076',
    '__Secure-1PSID': 'g.a0008gjhPfbzH1FITb7Hj_yG16Nl3RSTFH7RGujeHAdpqj8-mwn5JhasdF_BGxu-w0LkDVAibwACgYKASwSARASFQHGX2MiyRpnFym0vn9Z8gYknxiaZRoVAUF8yKrkyC1xSYqdqb0ODXPU7BW20076',
    '__Secure-3PSID': 'g.a0008gjhPfbzH1FITb7Hj_yG16Nl3RSTFH7RGujeHAdpqj8-mwn5NA4bptnkLgYdYYmJZqclxgACgYKAToSARASFQHGX2Midls_yBVkbECEg_QBYw_MDRoVAUF8yKpjUY5O-0tHfPyPHwHk-uCg0076',
    'HSID': 'AgZFvduUH-Ma9sBRf',
    'SSID': 'AVRaZjPbWUdXMQ-K-',
    'APISID': 'VXMmSsloKOyny7Ui/AoJx304betsto7_0e',
    'SAPISID': 'SmwuGKrrHHCDN9PN/AsKLVbvBBNJwXBPzN',
    '__Secure-1PAPISID': 'SmwuGKrrHHCDN9PN/AsKLVbvBBNJwXBPzN',
    '__Secure-3PAPISID': 'SmwuGKrrHHCDN9PN/AsKLVbvBBNJwXBPzN',
    'AEC': 'AaJma5tvm4lzoNYSdDxu0DvzsNGjiaqe14komyK7KWESs5jQamzQs9vvdA',
    'NID': '530=UF_tGhPagL_C7HQ2nwqSQ_-4Hlar0NTUhQUh7q5drgbEqJu36KQWD8d_SYroXBeB2ueimGG-CCEnxRF2OHfaiQ2DBNDGstYA7jw4Q_teShdmcEoCHXootx2PXn2xgqf6yCyFDjBoHvJv4urn4iOBMQhikYYzaWWCuGcXq1_nEMzuZ6y1blcCQiPgrNEUg1M4j4MjgSkH76ao9_wg-G1gB9xRSrg4ODORaW5o25gd07UjaSGKBSFE7jkUHfRD8Ibokj6J_UJr0nYRGlvBmGFrIOLlDHXFOhSi5twe9cLiWHszoMVNgioVUmDyCwekZtfUlMvAnl-ylp7eZqOdWV0HFUGWjb_fIew5V3aomK4BbkjsSgJSgobjSKUcWnuEQfS_xGIej9zaJRSCE4cFLRMfFIMyRC6Pmxyykn5K7HNg546RUlewSIa0mM1GdpPZCjzPG5Bkssk2wEOFYgb3NY1SVEcqAZo2hvu9CE-odxEnuQujXTJsLDLIekB3hyjZlK9omXY9ZDNrkjDrgKS00uq2kzGjJzHLYltgKhduVbqhCN1vzEUpnF_1B5WunQfrLfy3djz6YaUQKRlTEDM8kRmW2lWLAgOzISdiCXvbMsYObqGmHqI0fuKF17NCjLb2Fxax4hACqzvp4SMZI6gt0CzZOqWPtF5G1wu177eJrtiD_QMn_HOaCmnw491tMQFkHcMpFLrP_KiuSanB8nYZlYn4UYSMvEPJZgj4KXxFG0cvZr6cZuUHThNOFjKBOm28FXOjlfHOm_t_QsOr3YS8BnHw6Q0drp8CiFfXuXpnGDG3KWiRIeHNULaFIx2yHroBaPwO-qJRibZjCpSRRsNkWQ25sNJ6N0FOeXkLF3a-fjr7fO9O2AWehWaD8lBHOqjWA0mpkQOkDBuPtapbPZOXOtqtrEQ4VkovygyopvGhCe12XtEZCI8ohZSUtW2CcqG-a-deUhDW5kyTkfIMyRycX4w0G4Gl6dALJqAKEfQdTt1or8EYBoXa9GaKzFiJETu1WTyqIwNd4nYmtYMkn6Gyl5d1kyLeFSxyyBuEmIgGYnF_6Hwy7ahHjFE-V5sCoYgxtP38Uw7Z91kpgrTWrfRToOzg4bTmsEuAPbBJ0X04PyWXkuJLmZZE5lw8VvRzgIpyyq0GuL9lVcGGRvGjIWdHnzloxaJr8D6vm2td3nL6zbL3haQXR8wJyz0OBdt4KBfKhUMR_0PE2hZ-T0rTfX75BUkVgqx7jXemQg197FtSGe42oRZ8fQM9cDlHRHOV1LTngTmfz3n655ia2Yuc-hHAN2xhD1GyIkS-lEmSLUpfqkenXwT87hL7I2SNjueHY6fgSxJKQ8BZO_XB-zKjJWUYP-Q7W4ilUwJBSPNB6147b6wTMNR7sli9Zvfgwp5frW_y2bjESICTlK0BdtZVsUYeRCyh3z96ttWYHB4ruj5PGPhHYhCgbtAoh0Jh5gV0ao5yKdIlGbmMGY_Vk8YLd_IEGSyl16E-cOXuOd54atcz0nxCVLaM3z4bT-UKhoGVpT8tcWr568b_9m6_Ih2mrr3Ai92E67qGin-A50BydT3grScZBg6h-5qGboQUZaKaO2-fDhag2C4HjrOwO4qXED_wwZPh3IcLij46UCCUkWTeDK9woIM_wmzumusRkRwPyaT8VU5j8Zgwb0v8zm4Lhu9QERdUff7OHbwX9ee4yZy1EGBwthLU48gk3vnogwtGKPmjtTRWw17gf6fgWQI0GMh8yhlZP9QhVk2kmJBU4PUvZYpXr9B49tgw6ztg2bLcCNajj1lJ-EdILrWeCPFGxB3ZraAexajvTC3jMZnmd45LfrKkpv7NumzKzsefAqdQ5e4aE-HSLjcSeI56UyHHXKUH71_wcqwDszQp6ZIGNK29izeezmXfYQq8Vj8GQoxSoxGAuacTcD_gkKOVN9R5VYsMnghanz06RjdMTpDmCzUOVpe9gG_Wc48',
    '__Secure-1PSIDTS': 'sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA',
    '__Secure-1PSIDRTS': 'sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA',
    '__Secure-3PSIDTS': 'sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA',
    '__Secure-3PSIDRTS': 'sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA',
    'SIDCC': 'AKEyXzU3opIwrEOhEgkeFEx3cwlgQdNjR8AV_zi32hIRj6YPQOIa8LQfLsZJMQyLgzxJn0WvcaFP',
    '__Secure-1PSIDCC': 'AKEyXzX2e_U-1dT2HXpxuz4zXI9kL72mYSUgswPpecPE4YssoEf11BhJouEGzXIBuYshd8driow',
    '__Secure-3PSIDCC': 'AKEyXzWh-UUygmGmoocPu6oHH7IVODOADZiALlnholREGX0LxKqzeUSNoMDlLjDlEdYpRX_H-1Xt',
}

    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'origin': 'https://www.google.com',
        'priority': 'u=1, i',
        'referer': 'https://www.google.com/travel/flights/search?tfs=CBwQAhojEgoyMDI2LTA0LTI5agwIAhIIL20vMDRqcGxyBwgBEgNNWFBAAUgBcAGCAQsI____________AZgBAg&tfu=EgoIABABGAAgAigB&hl=en&gl=us',
        'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        'sec-ch-ua-arch': '""',
        'sec-ch-ua-bitness': '"64"',
        'sec-ch-ua-form-factors': '"Desktop"',
        'sec-ch-ua-full-version': '"146.0.7680.178"',
        'sec-ch-ua-full-version-list': '"Chromium";v="146.0.7680.178", "Not-A.Brand";v="24.0.0.0", "Google Chrome";v="146.0.7680.178"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-model': '"iPad"',
        'sec-ch-ua-platform': '"iOS"',
        'sec-ch-ua-platform-version': '"18.5"',
        'sec-ch-ua-wow64': '?0',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15',
        'x-browser-channel': 'stable',
        'x-browser-copyright': 'Copyright 2026 Google LLC. All Rights reserved.',
        'x-browser-validation': 'qd+J6eTTxowTDjaThrxRf9FBo/k=',
        'x-browser-year': '2026',
        'x-client-data': 'CKmdygEIk6HLAQiFoM0BCLC7zwEI17vPAQiVvM8BCLG+zwEYvqnKARiKqc8BGNa9zwE=',
        'x-goog-batchexecute-bgr': '[";DhC4EHTQAAbWHmw59h5fT5HyFN78bcMmAEABEArZ1PcMgM7lV_nL2L1OdSsIwdR8ZeoWmmLtR6viJIiMOsDGAdkWGjOzZ5XYcEhjHrEL2EnujmuJnfILsKfbHwAAAKVPAAAFnnUBB2MAQ20WTpWoVguW0qUOJkimNAazfAJgKTIYfrHkW3V6N2kyH1aaJ5Pmi9eiIvD-_y7620GO-H7NS-TuvlJ2w-UvnlcA6UyEA1-mOtkQYm1bibqEotGQxXEdb0NkQlbZt5wGTNQYRA7ATDMRnERUbOraDIKhhP292WMfhA0acMICHKO47RgxVBda0FIZA171h70CN-mfzZ-Idq7X39NrSbrhSVP9ix3BGkhkFthYNjprG9HhzAUvskLhXaLYe6dJn9hLXvwHw7sq_JESo67E7WDZaXv8r5QKtaM08Z6SNdVWKtKk0ho-V9smM9LYJNxhhtLdeB3G8DyHzA4HTeTiw1247BqhC4QAlgaF4IRTFekXvnyYfhlKHP-Dn5RuCr9wi-6JBTu0r8LFWqCRwFEitNSRqUos4X6UIml2t6fy2C3WBH3Xz086mrYM3UxsN6zTONGUErVH8-BRHQA4_ajA7ZuV8EHNWJieTxsk1iPSv1vu-Cb9pGJP4Xhf1whpT9YD04GYgDTc01ntLhkCeT6La3UZlLY-g9BxE0z2PDPm9Q3CbbPZqbVRXfxc5_m1VbYzY-Mt75nvapXFA6svkBQ3FYC5S3EX6dWzQucdfSGyNU20nBCFHZnOnMhMdqLgP39oPHnVURS5J8ZmQfHCSH2PTv4fpktyAn3fdscPDxtkbXJAwUYuZVevpQz5nm0deragPUy7OuENZL_eFzG6JIDqf9XrVvMbpO1xDgd_zBdw-k9VKvnVUZ9HyApdoeuDygGlqHZGeDtAMndYh9fLIJTFNOU06Y1HK7_P523_l_xpEhF6YCHRe9LFJ1z7dQ3mSOCyN7_CiyUt99XAS5IVbFOPskEW3dL-aSHGYr8apAHaUynt1jZOew_Ybz8aa-dzpte8C4ZToF_rUGxRNbTWY2daonsXHf2NL6W235CBR2Rmz8Huyt2nb8H51fi5H0xwgW8FCmNZf4gE0deNxCoiBf0VuN_AfZ35Jn1VMerGLDtv3KXIGHBZjL6s5EMmknA4JDy-uByFXNFEawyW04znS5dnVTvQvEcpy7gWGIQwdBmniGJzoGMuP2q3ihb90kOHyCCpeKUPeSnsZ7Jc5s5M0oJa8Ix2rrgTjDC9qBcizVGSnb6blUzbpcZ3zIFg_0sFHLtara9kRQb1E7WN9s8nVL4kI8U07HvbgXaP0TN8RjGO9yidJSJGL42HikKUtcdtbegIYbJDcloiqOMpIsuQMbxAmyCC8Y1rsjQr7Q",null,null,1468,null,null,null,0,"5"]',
        'x-goog-ext-259736195-jspb': '["en-US","US","USD",2,null,[-180],null,null,7,[]]',
        'x-same-domain': '1',
        'cookie': '__Secure-BUCKET=CCQ; OTZ=8543161_44_44__44_; SID=g.a0008gjhPfbzH1FITb7Hj_yG16Nl3RSTFH7RGujeHAdpqj8-mwn5dRWSJfciB4Z8Aps_nQ2Q1QACgYKAUUSARASFQHGX2Mi521OXrfIe2EYwt6uWC-Z-xoVAUF8yKrnNLARJYVI0JWDWQc4OTCk0076; __Secure-1PSID=g.a0008gjhPfbzH1FITb7Hj_yG16Nl3RSTFH7RGujeHAdpqj8-mwn5JhasdF_BGxu-w0LkDVAibwACgYKASwSARASFQHGX2MiyRpnFym0vn9Z8gYknxiaZRoVAUF8yKrkyC1xSYqdqb0ODXPU7BW20076; __Secure-3PSID=g.a0008gjhPfbzH1FITb7Hj_yG16Nl3RSTFH7RGujeHAdpqj8-mwn5NA4bptnkLgYdYYmJZqclxgACgYKAToSARASFQHGX2Midls_yBVkbECEg_QBYw_MDRoVAUF8yKpjUY5O-0tHfPyPHwHk-uCg0076; HSID=AgZFvduUH-Ma9sBRf; SSID=AVRaZjPbWUdXMQ-K-; APISID=VXMmSsloKOyny7Ui/AoJx304betsto7_0e; SAPISID=SmwuGKrrHHCDN9PN/AsKLVbvBBNJwXBPzN; __Secure-1PAPISID=SmwuGKrrHHCDN9PN/AsKLVbvBBNJwXBPzN; __Secure-3PAPISID=SmwuGKrrHHCDN9PN/AsKLVbvBBNJwXBPzN; AEC=AaJma5tvm4lzoNYSdDxu0DvzsNGjiaqe14komyK7KWESs5jQamzQs9vvdA; NID=530=UF_tGhPagL_C7HQ2nwqSQ_-4Hlar0NTUhQUh7q5drgbEqJu36KQWD8d_SYroXBeB2ueimGG-CCEnxRF2OHfaiQ2DBNDGstYA7jw4Q_teShdmcEoCHXootx2PXn2xgqf6yCyFDjBoHvJv4urn4iOBMQhikYYzaWWCuGcXq1_nEMzuZ6y1blcCQiPgrNEUg1M4j4MjgSkH76ao9_wg-G1gB9xRSrg4ODORaW5o25gd07UjaSGKBSFE7jkUHfRD8Ibokj6J_UJr0nYRGlvBmGFrIOLlDHXFOhSi5twe9cLiWHszoMVNgioVUmDyCwekZtfUlMvAnl-ylp7eZqOdWV0HFUGWjb_fIew5V3aomK4BbkjsSgJSgobjSKUcWnuEQfS_xGIej9zaJRSCE4cFLRMfFIMyRC6Pmxyykn5K7HNg546RUlewSIa0mM1GdpPZCjzPG5Bkssk2wEOFYgb3NY1SVEcqAZo2hvu9CE-odxEnuQujXTJsLDLIekB3hyjZlK9omXY9ZDNrkjDrgKS00uq2kzGjJzHLYltgKhduVbqhCN1vzEUpnF_1B5WunQfrLfy3djz6YaUQKRlTEDM8kRmW2lWLAgOzISdiCXvbMsYObqGmHqI0fuKF17NCjLb2Fxax4hACqzvp4SMZI6gt0CzZOqWPtF5G1wu177eJrtiD_QMn_HOaCmnw491tMQFkHcMpFLrP_KiuSanB8nYZlYn4UYSMvEPJZgj4KXxFG0cvZr6cZuUHThNOFjKBOm28FXOjlfHOm_t_QsOr3YS8BnHw6Q0drp8CiFfXuXpnGDG3KWiRIeHNULaFIx2yHroBaPwO-qJRibZjCpSRRsNkWQ25sNJ6N0FOeXkLF3a-fjr7fO9O2AWehWaD8lBHOqjWA0mpkQOkDBuPtapbPZOXOtqtrEQ4VkovygyopvGhCe12XtEZCI8ohZSUtW2CcqG-a-deUhDW5kyTkfIMyRycX4w0G4Gl6dALJqAKEfQdTt1or8EYBoXa9GaKzFiJETu1WTyqIwNd4nYmtYMkn6Gyl5d1kyLeFSxyyBuEmIgGYnF_6Hwy7ahHjFE-V5sCoYgxtP38Uw7Z91kpgrTWrfRToOzg4bTmsEuAPbBJ0X04PyWXkuJLmZZE5lw8VvRzgIpyyq0GuL9lVcGGRvGjIWdHnzloxaJr8D6vm2td3nL6zbL3haQXR8wJyz0OBdt4KBfKhUMR_0PE2hZ-T0rTfX75BUkVgqx7jXemQg197FtSGe42oRZ8fQM9cDlHRHOV1LTngTmfz3n655ia2Yuc-hHAN2xhD1GyIkS-lEmSLUpfqkenXwT87hL7I2SNjueHY6fgSxJKQ8BZO_XB-zKjJWUYP-Q7W4ilUwJBSPNB6147b6wTMNR7sli9Zvfgwp5frW_y2bjESICTlK0BdtZVsUYeRCyh3z96ttWYHB4ruj5PGPhHYhCgbtAoh0Jh5gV0ao5yKdIlGbmMGY_Vk8YLd_IEGSyl16E-cOXuOd54atcz0nxCVLaM3z4bT-UKhoGVpT8tcWr568b_9m6_Ih2mrr3Ai92E67qGin-A50BydT3grScZBg6h-5qGboQUZaKaO2-fDhag2C4HjrOwO4qXED_wwZPh3IcLij46UCCUkWTeDK9woIM_wmzumusRkRwPyaT8VU5j8Zgwb0v8zm4Lhu9QERdUff7OHbwX9ee4yZy1EGBwthLU48gk3vnogwtGKPmjtTRWw17gf6fgWQI0GMh8yhlZP9QhVk2kmJBU4PUvZYpXr9B49tgw6ztg2bLcCNajj1lJ-EdILrWeCPFGxB3ZraAexajvTC3jMZnmd45LfrKkpv7NumzKzsefAqdQ5e4aE-HSLjcSeI56UyHHXKUH71_wcqwDszQp6ZIGNK29izeezmXfYQq8Vj8GQoxSoxGAuacTcD_gkKOVN9R5VYsMnghanz06RjdMTpDmCzUOVpe9gG_Wc48; __Secure-1PSIDTS=sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA; __Secure-1PSIDRTS=sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA; __Secure-3PSIDTS=sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA; __Secure-3PSIDRTS=sidts-CjYBWhotCTWeJu9Kb7DPZPYMGisv2OoUwuMY7ENb0yEKqwWpxIHOiCci_TZWm-C6SNpxupo_3IAQAA; SIDCC=AKEyXzU3opIwrEOhEgkeFEx3cwlgQdNjR8AV_zi32hIRj6YPQOIa8LQfLsZJMQyLgzxJn0WvcaFP; __Secure-1PSIDCC=AKEyXzX2e_U-1dT2HXpxuz4zXI9kL72mYSUgswPpecPE4YssoEf11BhJouEGzXIBuYshd8driow; __Secure-3PSIDCC=AKEyXzWh-UUygmGmoocPu6oHH7IVODOADZiALlnholREGX0LxKqzeUSNoMDlLjDlEdYpRX_H-1Xt',
    }
    try:
        if http_proxy and http_proxy != 'No proxy':
            proxies = {
            'http': http_proxy,
            }
            res = requests.get(url, proxies=proxies, timeout=90) 
        else:
            res = requests.get(url, timeout=90)    
        return res.text
    except Exception as e:
        print(e)
    return None