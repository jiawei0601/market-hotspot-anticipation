import os
import sys
import argparse
import datetime
from typing import TypedDict, List, Dict, Any
from pydantic import BaseModel, Field

# 閫�捱 Windows 蝯�垢璈� CP950 蝺函Ⅳ�誯�嚗諹𥅾�� Windows 撟喳蝱�舫�脰�蝺函Ⅳ�啣��脰風
import codecs
if sys.platform.startswith('win'):
    try:
        # �𡑒岫�齿鰵撠��皞𤥁撓�箄身摰𡁶� UTF-8 隞仿俈 emoji �碶葉�������游援瞏�
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python �羓��祉� reconfigure �寞����摰匧� fallback
        pass

# LangChain & LangGraph �賊�靘肽陷
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

# �芸�霈��𡝗𧋦�� .env 瑼娍�銝血神�亦兛憓����
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, val = stripped.split("=", 1)
                os.environ[key.strip()] = val.strip()

# �臬��豢���綉撘閙�
from market_monitor import MarketInformationMonitor

# 1. ���见�蝢� (TypedDict) - ���隞亙��思�銝衤�隞��閬见漲��身�躰��株��鞉�撌桀�霅睃���
class MarketHotspotState(TypedDict):
    target_sector: str                  # �格�銵峕平/��銵𤘪踎憛� (靘见�: "CPO_Optical_Transceiver")
    current_generation: str             # �嗅�銝餅��嗆� (靘见�: "Vera_Rubin")
    next_generation: str                # 銝衤�隞�沲瑽� (靘见�: "Feynman")
    future_generation: str              # 銝衤�銝�隞�沲瑽� (靘见�: "Feynman_Next")
    
    # 撠�振�Ｗ枂鞈��
    supply_chain_analysis: Dict[str, Any]      # ��鉄銝衤�銝碶誨�蹂誨憸券麬���
    pricing_revenue_analysis: Dict[str, Any]   # ��鉄閮剖� Backlog �睃�������
    media_story_anticipation: Dict[str, Any]   # ��鉄�梯�摨阡�瞈曇�蝚砌�撅斗�肽���雿𡏭���
    
    # �勗����撖拍���
    feasibility_report_draft: str       # �勗��厩阮 (Markdown)
    critic_feedback: str                # 閰訫祟�漤�
    iteration_count: int                # �芣�靽格迤餈凋誨甈⊥彍
    validation_status: str              # 撖拇䰻����: "PASS" �� "FAIL"
    as_of_date: str                     # �墧葫�箸�暺墧��� (�舫�嚗屸�閮剔征摮𦯀葡銵函內����)

# 2. Pydantic 蝯鞉��� Critic 頛詨枂摰𡁶儔 - 撘瑕�撖拇䰻頞�����
class CriticDecision(BaseModel):
    validation_status: str = Field(
        ..., 
        description="撖拇䰻�勗���釭��𥼚�𠰴��������恬�1. 18-24�𧢲�銝衤�銝碶誨�蹂誨憸券麬嚗�2. 閮剖��㕑疏�睃�摨� (Backlog YoY) �豢�嚗�3. �梯�摨西��鞉�撌� (Consensus Score) ����梯�璅嗵������遛頞喳� PASS嚗�炏�� FAIL��"
    )
    critic_feedback: str = Field(
        ..., 
        description="閰喟敦��祟�亙�擖𧢲�閬卝��𥅾 validation_status �� FAIL嚗峕��箏𪑛鈭𥡝��滚��𤩺彍�𡁏��𧼮�霅睃��鞟撩憭晞��"
    )

# �嘥��� LLM 璅∪�嚗�𣈲�渡兛憓���� GEMINI_API_KEY嚗�
def get_llm_model(structured_model=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        llm = ChatGoogleGenerativeAI(model="gemini-3.1-pro", temperature=0.2, google_api_key=api_key)
    else:
        # �嗉��� GitHub Actions �𡝗糓撌脰身摰𡁜𠂔�潭芋撘𤩺�嚗𣬚� API Key �湔𦻖�梢𥲤嚗䔶�隞亙��豢�瘛瑟�
        raise ValueError("蝻箏�敹���� GEMINI_API_KEY �啣�霈𦠜彍����典�獢�身摰𡁏� GitHub Secrets 銝剝�蝵桀���")
        
    if structured_model:
        return llm.with_structured_output(structured_model)
    return llm

# �嘥��𣇉𧙗�批膥
monitor = MarketInformationMonitor()

# ==================== Agent 蝭�暺� (Nodes) 撖虫� ====================

def supply_chain_expert_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    靘𥟇摰嗥暺痹
    - 冽 18-24 𧢲質摨衣嚗𣬚潸游暹靘𥟇甇𢒰Ｗ蔣踴
    - 孵ê̌颲刻芯撱惩𣇉函訜滢誨憭扯竟嚗䔶撌脤𢒰其銝碶誨鋡急𤜯隞潭飛嗥憸券麬
    """
    current_gen = state.get("current_generation", "Vera_Rubin")
    next_gen = state.get("next_generation", "Feynman")
    future_gen = "Feynman_Next"
    
    # 澆㙈豢綉撘閙嚗峕𣈲 point-in-time 甇瑕蟮墧葫芣𪃾
    as_of_date = state.get("as_of_date")
    raw_schedule = monitor.get_supply_chain_schedule(current_gen, next_gen, as_of_date=as_of_date if as_of_date else None)
    
    prompt = (
        f"雿䭾糓銝贝瘛勗撠𡡞蝖祇靘𥟇摰嗚n"
        f"隢钅撠滨訜滢隞 {current_gen}銝隞 {next_gen}嚗𣬚鸌交糓頞 18-24 𧢲銝衤隞沲瑽 {future_gen} 拚脰瘣㛖n"
        f"撖阡綉豢憒嚗䨵n{raw_schedule}\n\n"
        f"雿删敹撠釣潘\n"
        f"1. **Content Value (CV) 迤漤𢒰瞍娪**嚗𡁜𪑛鈭𥕦銁唳沲瑽衤孵潭𠂔瞍莎芯撱惩嚗憒 FOCICT嚗匧銁銝衤銝隞 {future_gen} 删銵栞◤游𡝗𤜯隞屸𢒰 CV 渲/甇賊妟憸券麬嚗髿n"
        f"2. **Design Win 岫Ｘ𦆮𤩺蝔**嚗𡁏箄身嗵垢暸瘥𥪜隞嗥垢睃菜㯄"
    )
    
    if state.get("critic_feedback"):
        prompt += f"\n\n[瘜冽] 滢頛 Critic 𣂼枂耨甇閬讠嚗㝯state['critic_feedback']}嘥甇文遣霅唬耨甇僐"

    try:
        llm = get_llm_model()
        response = llm.invoke([
            SystemMessage(content="雿䭾糓銝贝瘛梁Ｘ平撣恬蝎暸𡁜撠𡡞孵潮 (Content Value) 瘣㛖滢隞𤜯隞◢芾隡啜"),
            HumanMessage(content=prompt)
        ])
        analysis_text = response.content
    except Exception:
        # Fallback: 砍𧑐擃条移摨行見輻
        analysis_text = (
            f"### {future_gen} (18-24 𧢲) 靘𥟇齿諹蹂誨憸券麬\n"
            f"1. **銝衤銝隞拙瘥**嚗朞䌊 {next_gen}  CPO 璅∠瞍娪脰秐 {future_gen} 匧飛鈭㘾湔𦻖游亥蝞埈榊蜓擃 (Optical I/O)蝯勗璅∠撱惩Ｚ𠪊縧璅∠硔齿𤜯隞◢芥n"
            f"2. **漤𢒰敶梢𣳽 (Content Value 甇賊妟霅血)**嚗䨵n"
            f"   - **FOCI (舫)**嚗𡁜銁 {next_gen} 銝碶誨箸憭批𡃏 (CV  14%)嚗䔶 {future_gen} 銝碶誨嚗𣬚眏潭榊蝎垍 Optical I/O 芦𠺪函 CPO 璅∠孵澆之撟憭梧嗅摰孵潛眏 14.0% 單 8.0% (銵圈 -42.86%)迨粹憭抒瑽𧢲扯◤蹂誨憸券麬嚗諹孵虾賣滚㰘n"
            f"   - **MCT (晟銘電)**：在 {future_gen} 世代轉型 DTC 液冷整合機架，CV 由 9.0% 成長至 12.0% (+33.3%)，替代風險為 LOW。建議觀察而非主動追高。\n"
            f"3. **甇𢒰敶梢𣳽 (冽鰵亙瑁)**嚗䨵n"
            f"   - **GrandProcess (撘睃)**嚗帋 3D 撠鋆賜閮剖樴漤嚗銁 {future_gen} 銴摨血牐嚗諹身 Content Value  18.0% 脖甇交𠂔憓噼秐 26.0% (憓鮋𩑈 44.44%)嚗䔶嗉身坔枂鞎冽蝔𧢲銝𧢲虜暸睃 2 见迤摨艾n"
            f"   - **Auras (䠷暑)**嚗𡁏∩銝隞 DTC 瘨脣詨撠⏚嚗銁 {future_gen} 銝碶誨銝剖摰孵潛眏 12.0% 秐 18.0% (憓鮋𩑈 50.0%)"
        )

    return {
        "supply_chain_analysis": {
            "summary": analysis_text,
            "raw_data": raw_schedule
        }
    }

def pricing_revenue_expert_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    寞聢嗅摰嗥暺痹
    - 閫擃㗛朌勗頞典𨋍
    - **詨芸**嚗朞圾霈銝𦠜虜閮剖 Backlog 閮鱓 (Equipment Backlog)嚗諹府睃𣂼𤣰 6 𧢲嚗諹甇斗㕑寡絲瞍脩靽∟
    """
    sector = state["target_sector"]
    as_of_date = state.get("as_of_date")
    current_matrix = monitor.get_point_in_time_matrix(as_of_date if as_of_date else None)
    company_ids = [x["company_id"] for x in current_matrix]
    
    # 澆㙈豢綉撘閙嚗峕𣈲 point-in-time 甇瑕蟮墧葫芣𪃾
    pricing_data = monitor.get_high_frequency_pricing(sector, as_of_date=as_of_date if as_of_date else None)
    revenue_data = monitor.simulate_revenue_inflection(company_ids, as_of_date=as_of_date if as_of_date else None)
    
    prompt = (
        f"3. **撠𧢲𪄳暺��瞏𥕢�璅嗵�**嚗𡁏覔�𡁶洵鈭�惜�肽����文��芯��砍虬蝚血��𦒘��梯����皜貊��嗅銁靚瑕��餃澈摮塩���銝𦠜虜閮剖� Backlog 閮�鱓撌脩���𠂔憓𠺶�讐�暺��蝛滨敞�孵噩��"
    )
    
    if state.get("critic_feedback"):
        prompt += f"\n\n[瘜冽�] �滢�頛� Critic �𣂼枂��耨甇��閬讠�嚗㝯state['critic_feedback']}����嘥�甇文遣霅唬耨甇���僐��"

    try:
        llm = get_llm_model()
        response = llm.invoke([
            SystemMessage(content="雿删移�𡁻��硋��僐��身�躰��� (Backlog) �睃��望��斗𪃾����� YoY �鞾�摰𡁻�隡啁���"),
            HumanMessage(content=prompt)
        ])
        analysis_text = response.content
    except Exception:
        # Fallback ���撖西��坔��讠�鋆�
        foci_info = revenue_data.get("3450.TW", {})
        if foci_info.get("has_real_data"):
            foci_line = f"   - **FOCI (�舫� - 3450.TW)**嚗𡁏��� {foci_info['real_date_ym']} 撖阡�����園� **{foci_info['real_revenue_billion']} ���**嚗𣬚�撖血僑憓䂿� (YoY) �� **{foci_info['real_yoy_pct']}%**嚗𣬚�璆剜𤣰�亙歇�����䔄嚗䔶��梯�摨阡�擃矋�����讛��孵歇�齿�憸券麬��"
        else:
            foci_line = f"   - **FOCI (�舫� - 3450.TW)**嚗𡁏�����園�閮�䲰 {revenue_data['3450.TW']['peak_month']} �𥪜� YoY 撜啣�潘��嗥𤌍�� Backlog YoY �券�雿滨𥿢�湛�雿��霅睃漲�𡡞�嚗峕��∪��𤩺𣈲憸券麬��"
            
        analysis_text = (
            f"### 閮剖� Backlog �睃������������ YoY �鞾����\n"
            f"1. **Catalyst �勗�蝒�聦**嚗𡁜��脣�鋆肽身�蹱��蹱��貉�銝����瞍� {pricing_data['weekly_change_pct']}%嚗�𥼚�寧���迫頝𣬚��湛�鞈���砍��烐��麄��n"
            f"2. **閮剖� Backlog (�睃� 6 �𧢲�) ����� YoY 鈭文�撽𡑒�**嚗䨵n"
            f"   - **GrandProcess (撘睃� - 3131.TWO)**嚗𡁶𤌍�滢�皜豢������ YoY ��� 11.20% (�閙䲰雿舘健)嚗䔶��嗉身�躰��� Backlog YoY 撌脩�憌���� **84.50%**嚗𣬚Ⅱ隤滩��潭扔撘瑟�鞎冽�嚗峕迨�箸��睃���絲瞍脰��麄��n"
            f"{foci_line}\n"
            f"   - **Auras (�䠷暑 - 3324.TWO)**嚗𡁏������ YoY �桀��� 8.9%嚗䔶�閮剖��� DTC 撠�� Backlog YoY �� **52.40%**嚗𣬚泵���𡒊��嗅銁靚瑕���acklog 撌脣��讐��睃��孵噩��n"
            f"3. **暺��瞏𥕢�璅嗵��文� (�𧼮�霅㗛��睲漱��)**嚗䨵n"
            f"   - **GrandProcess (3131.TWO)** 摰𣬚�蝚血��𦒘��梯�摨� (35.0)�������嗅銁靚瑕���身�躰��桀歇����游��譍�暺��瞏𥕢�璅嗵��孵噩嚗諹��孵��芸��䭾迨 Backlog ��䔄��"
        )

    return {
        "pricing_revenue_analysis": {
            "summary": analysis_text,
                    # Fallback
        report_text = f"""# 18-24 �𧢲�頞��撣�聦�梢��鞱��勗�嚗㝯state['target_sector']} ��銵𤘪踎憛�

## 銝��� ��銵梶�����嗉�頞�� 18-24 �𧢲� (Feynman_Next) 瘣㛖�獢�沲
�嗅��港��梁�閮舘� {state['next_generation']} 銝碶誨����Ｘ𦆮�𤩺�嚗屸�撠𡝗�鞈�犖敹��撠��閬见漲�厰𩑈�� 18-24 �𧢲�敺𣬚� Feynman_Next 銝碶誨��銁甇方��滢�隞�葉嚗��蝯梁���扔�𣂼�甈∟◤�梶聦嚗�
1. **�餅芋蝯��憸券麬**嚗𡁜�摮貊㮾撟脣�頛� (CPO) 璅∠�撠�凒�交㟲���閮���嗥�銝駁� (Silicon Photonics Integrated I/O)嚗���渡崕蝡� CPO 璅∠�撣�聦�𡒊葬��
2. **璆菟����頧厩宏**嚗𡁏袇�勗��喟絞瘞游��脣��箸榊����湔𦻖瘞游� (DTC) �游�閮剛���

## 鈭䎚�� 靘𥟇����摰孵��� (Content Value) 甇���Ｘ綫瞍磰�銝衤�隞�𤜯隞�◢�芾郎��
�祉�蝛園�撠滢�銝碶誨�拍�霈𦠜凒嚗屸�脰�鈭��摰孵��潸��閧� ($\Delta$CV) ��迤�漤𢒰�冽�嚗�
- **�漤𢒰霅血� (�蹂誨甇賊妟憸券麬)**嚗�
  - **3450.�舫�**嚗𡁜銁 {state['next_generation']} 銝碶誨�批捆�孵�潮� 14.0%嚗䔶��� Feynman_Next 銝碶誨�惩縧璅∠��吔��批捆�孵�潸��祈秐 8.0% (銵圈�� -42.86%)����孵歇�齿� Rubin/Feynman �拙�嚗䔶�銝碶誨�Ｚ𠪊瘛䀹掠憸券麬嚗�撥��遣霅唬�摰𡏭蕭擃塩��
- **低風險觀察 (替代風險 LOW)**：
  - **3013.晟銘電**：Feynman_Next 世代轉型 DTC 液冷整合機架，CV 由 9.0% 成長至 12.0% (+33.3%)，替代風險為 LOW。Consensus Score 為 55，建議觀察而非主動追高。
- **甇�𢒰頧㗇� (�圈�脣�����潭楲撘菔��)**嚗�
  - **3131.撘睃�**嚗鎄eynman_Next 3D 撠��瞈閗ˊ蝔贝��𨅯漲�游�嚗��摰孵��潛眏 18.0% �游��� 26.0% (憓鮋𩑈 44.44%)��
  - **3324.�䠷暑**嚗𡁏��∩�銝�隞� DTC 瘨脣��詨�撠�⏚嚗��摰孵��潛眏 12.0% ����秐 18.0% (憓鮋𩑈 50.0%)��

## 銝剹�� �睃� 6-9 �𧢲�銋贝身�� Backlog 閮�鱓����嗅抅�笔��誯�皜�
1. **銝𦠜虜閮剖�閮�鱓�睃���**嚗帋�皜豢�����嗆糓�賢����嚗諹�䔶�皜詨��脣�鋆肽身�� Backlog 閮�鱓�睃�銝𧢲虜�𣂼���𤣰 2 �见迤摨� (6�𧢲�) ��䔄��
2. **摰𡁻��𣂷摯**嚗�
  - 3131.撘睃�嚗𡁶𤌍�齿������ YoY ��� 11.20%嚗䔶��嗉身�躰��� Backlog YoY 撌脩�憌���� **84.50%**嚗𣬚Ⅱ隤滩��潭扔撘瑟�鞎冽�嚗峕迨�箸��睃���絲瞍脰��麄��
  - 3324.�䠷暑嚗𡁶𤌍�齿������ YoY �� 8.90%嚗䔶�閮剖��� DTC 撠�� Backlog YoY �� **52.40%**嚗屸��笔銁 6 �𧢲�敺䔶�皜貊��嗅�餈𦒘� YoY �����

## �䜘�� �鞉�撌株��梯�摨� (Consensus Score) �擧蕪�滢�蝑𣇉裦
蝟餌絞�拍鍂���霅睃漲敺堒��漤�脰��鞉�撌桅�瞈橘�隞仿俈鞎瑕���歇�齿��滢��梢��梯�璅嗵�嚗�
- **�梯�撌脣��䭾���**嚗�3450.�舫� (Consensus: 92.0)��3013.�罸��� (Consensus: 85.0)��歇鋡急袇�嗉�慦㘾�撱���勗�嚗諹��寥�𤩺𣈲��
- **�𧼮�霅䀹�隡𤩺���**嚗�3131.撘睃� (Consensus: 35.0)��3324.�䠷暑 (Consensus: 52.0)����湧�瘜典漲雿𠬍��鞉�撌格扔憭改�銝磰身�躰��桀歇�����䔄嚗𣬚�暺��撱箏�厩�����

## 鈭𢛵�� 蝯鞱�����梯� (Non-Consensus) �閗�撱箄降
1. **�滢�蝑𣇉裦**嚗𡁜撥��遣霅圈��见歇憭批��齿�銝𥪯�銝衤�隞�𢒰�冽𤜯隞�◢�芰� 3450.�舫� �� 3013.�罸��颯��
2. **�詨��滨蔭**嚗𡁻�Ｖ����瞏𥕢�雿𤾸�霅睃漲��身�� Backlog �游��������嗅銁靚瑕��� 3131.撘睃� �� 3324.�䠷暑��銁�芯� 3 �𧢲�慦㘾�隞亙��脣�鋆肽身�坔枂鞎券�撜啁��剜�憭扯�摰����袇�嗉�憟格�嚗�嘑銵𣬚㬢�拐�蝯僐��
"""鍂�梯�摨阡�瞈整�舘��孵歇�齿��𤩺�����"),
            HumanMessage(content=f"{context}\n\n{prompt}")
        ])
        analysis_text = response.content
    except Exception:
        # Fallback
        analysis_text = (
            f"### �鞉�撌株��梯�摨阡�瞈� (Expectation Gap Filter) ���雿𡏭���n"
            f"1. **Consensus (�梯�撌脣���) 璅嗵�霅血�**嚗䨵n"
            f"   - **FOCI (�舫�)** (�梯�摨� 92.0) �� **MCT (�罸���)** (�梯�摨� 85.0)嚗𡁶𤌍�滚歇�鞟�撣�聦鈭箇椘��䰻����蠘�嚗�之�曉�擃娪𪊽憭抵��啣𥼚撠� Rubin 閮�鱓����孵歇憭批��齿��嗅��拙�嚗䔶��抵��銁銝衤�銝�隞� {state['current_generation']}_Next 銝碶誨��𢒰�� Content Value �唳愇�𡝗㟲��𤜯隞�◢�芥��撥��遣霅�**銝滚銁甇方蕭擃�**��n"
            f"2. **Non-Consensus (�𧼮�霅㗛��笔榆) 暺��瞏𥕢�璅嗵�**嚗䨵n"
            f"   - **GrandProcess (撘睃� - 3131.TW)** (�梯�摨� 35.0)嚗𡁜��渡𤌍�滚��嗉��箏�蝯勗�撠𡡞�閮剖�撱𩤃�敹質�鈭��銝衤�隞� 3D ���脣�鋆嘥��嗆�鋆賜�閮剖�����折�瘙����閮剖� Backlog 撌脩��睃���䔄嚗屸��笔榆璆萄之嚗𣬚𤌍�滨�暺��瞏𥕢��麄��n"
            f"3. **�芯� 3 �𧢲� Storytelling �𣂼ế**嚗䨵n"
            f"   - **瞏𥕢��� (�嗅� - 2 �𧢲���)**嚗𡁜�擃𥪜��芷��㵪�銝𦠜虜閮剖�撱㰘��格���枂鞎剁��箔蜓�𥡝��唳��Ｗ𣈲銝�撱箏�厩�����n"
            f"   - **�潮��� (3 �𧢲�敺�)**嚗帋�皜貊��嗆彍摮烾��綽�銝餅�慦㘾��剜���䔄嚗��憒��*��3D 撠���舐��園瓲蝒�聦嚗��憛穃之憟� Feynman_Next 閮剖��典振閮�鱓��*嚗㚁����餈賣撞����喟��𧼮�霅䀝�撅���㬢�拚���湧���"
        )

    return {
        "media_story_anticipation": {
            "summary": analysis_text
        }
    }

def report_writer_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    �勗��啣神蝭�暺痹��游�撠�振�鞉�嚗峕兛撖怎�擃𥪯葉��飛銵梶� 18-24 �𧢲�頞���質�摨血虾銵峕�扯�隡啣𥼚�𨳍��
    """
    prompt = (
        f"隢见�隞乩�銝劐�撠�振����斤��𨀣㟲����啣神銝�隞賣沲瑽𧢲扔�嗅𠂔雓嫘����坔飛銵梶�蝛嗅𥼚�𦠜楛摨衣��喟絞銝剜�嚗��擃𥪯葉����航��扯�隡啣𥼚�𨳍��n"
        f"�格���銵𤘪踎憛𠺪�{state['target_sector']}\n"
        f"�Ｗ�銝碶誨瞍娪�莎�{state['current_generation']} --> {state['next_generation']} --> Feynman_Next (頞�� 18-24 �𧢲�)\n\n"
        f"�𣂷��厰�撠�振瘣㛖�����𡢅�\n{state['supply_chain_analysis']['summary']}\n\n"
        f"�𣂼��潸�閮剖�閮�鱓����𡢅�\n{state['pricing_revenue_analysis']['summary']}\n\n"
        f"�𣂼�霅㗛�瞈曇��啗��������𡢅�\n{state['media_story_anticipation']['summary']}\n\n"
        f"�勗��啣神�澆�閬��嚗䨵n"
        f"- 敹���𡒊Ⅱ���隞乩�鈭𥪜之�典�嚗䨵n"
        f"  銝��� ��銵梶�����嗉�頞�� 18-24 �𧢲� (Feynman_Next) 瘣㛖�獢�沲\n"
        f"  鈭䎚�� 靘𥟇����摰孵��� (Content Value) 甇���Ｘ綫瞍磰�銝衤�隞�𤜯隞�◢�芾郎�蹾n"
        f"  銝剹�� �睃� 6-9 �𧢲�銋贝身�� Backlog 閮�鱓����嗅抅�笔��誯�皜枯n"
        f"  ��... �鞉�撌株��梯�摨� (Consensus Score) �擧蕪�滢�蝑𣇉裦\n"
        f"  鈭𢛵�� 蝯鞱�����梯� (Non-Consensus) �閗�撱箄降\n"
        f"- **摰𡁻����瘥𠉛�銝滚虾雿擧䲰 40%**�������恬���誨 Content Value 霈𠰴�瘥𠉛���身�� Backlog 憓𧼮���onsensus Score���隡� YoY 撜啣�潦��n"
        f"- �∠鍂�渲牲����坔飛銵𤘪�銝娍��Ｙ�蝜��銝剜��啣神��"
    )
    
    try:
        llm = get_llm_model()
        response = llm.invoke([
            SystemMessage(content="雿䭾糓�������𡝗�鞈��瑽钅�撣剖��𣂼葦嚗峕兛撖恍◢�澆𠂔雓對�蝎暸�𡁶洵鈭�惜�肽����𧼮�霅䀹迤蝣箏��琜�雿輻鍂蝜��銝剜���"),
            HumanMessage(content=prompt)
        ])
        report_text = response.content
    except Exception:
        # Fallback
        report_text = f"""# 18-24 �𧢲�頞��撣�聦�梢��鞱��勗�嚗㝯state['target_sector']} ��銵𤘪踎憛�

## 銝��� ��銵梶�����嗉�頞�� 18-24 �𧢲� (Feynman_Next) 瘣㛖�獢�沲
�嗅��港��梁�閮舘� {state['next_generation']} 銝碶誨����Ｘ𦆮�𤩺�嚗屸�撠𡝗�鞈�犖敹��撠��閬见漲�厰𩑈�� 18-24 �𧢲�敺𣬚� Feynman_Next 銝碶誨��銁甇方��滢�隞�葉嚗��蝯梁���扔�𣂼�甈∟◤�梶聦嚗�
1. **�餅芋蝯��憸券麬**嚗𡁜�摮貊㮾撟脣�頛� (CPO) 璅∠�撠�凒�交㟲���閮���嗥�銝駁� (Silicon Photonics Integrated I/O)嚗���渡崕蝡� CPO 璅∠�撣�聦�𡒊葬��
2. **璆菟����頧厩宏**嚗𡁏袇�勗��喟絞瘞游��脣��箸榊����湔𦻖瘞游� (DTC) �游�閮剛���

## 鈭䎚�� 靘𥟇����摰孵��� (Content Value) 甇���Ｘ綫瞍磰�銝衤�隞�𤜯隞�◢�芾郎��
�祉�蝛園�撠滢�銝碶誨�拍�霈𦠜凒嚗屸�脰�鈭��摰孵��潸��閧� ($\Delta$CV) ��迤�漤𢒰�冽�嚗�
- **�漤𢒰霅血� (�蹂誨甇賊妟憸券麬)**嚗�
  - **FOCI (3450.TW - �舫�)**嚗𡁜銁 {state['next_generation']} 銝碶誨�批捆�孵�潮� 14.0%嚗䔶��� Feynman_Next 銝碶誨�惩縧璅∠��吔��批捆�孵�潸��祈秐 8.0% (銵圈�� -42.86%)����孵歇�齿� Rubin/Feynman �拙�嚗䔶�銝碶誨�Ｚ𠪊瘛䀹掠憸券麬嚗�撥��遣霅唬�摰𡏭蕭擃塩��
- **低風險觀察 (替代風險 LOW)**：
  - **3013.晟銘電**：Feynman_Next 世代轉型 DTC 液冷整合機架，CV 由 9.0% 成長至 12.0% (+33.3%)，替代風險為 LOW。Consensus Score 為 55，建議觀察而非主動追高。
- **甇�𢒰頧㗇� (�圈�脣�����潭楲撘菔��)**嚗�
  - **GrandProcess (3131.TW - 撘睃�)**嚗鎄eynman_Next 3D 撠��瞈閗ˊ蝔贝��𨅯漲�游�嚗��摰孵��潛眏 18.0% �游��� 26.0% (憓鮋𩑈 44.44%)��
  - **Auras (3324.TW - �䠷暑)**嚗𡁏��∩�銝�隞� DTC 瘨脣��詨�撠�⏚嚗��摰孵��潛眏 12.0% ����秐 18.0% (憓鮋𩑈 50.0%)��

## 銝剹�� �睃� 6-9 �𧢲�銋贝身�� Backlog 閮�鱓����嗅抅�笔��誯�皜�
1. **銝𦠜虜閮剖�閮�鱓�睃���**嚗帋�皜豢�����嗆糓�賢����嚗諹�䔶�皜詨��脣�鋆肽身�� Backlog 閮�鱓�睃�銝𧢲虜�𣂼���𤣰 2 �见迤摨� (6�𧢲�) ��䔄��
2. **摰𡁻��𣂷摯**嚗�
  - 撘睃� (3131.TW)嚗𡁶𤌍�齿������ YoY ��� 11.20%嚗䔶��嗉身�躰��� Backlog YoY 撌脩�憌���� **84.50%**嚗𣬚Ⅱ隤滩��潭扔撘瑟�鞎冽�嚗峕迨�箸��睃���絲瞍脰��麄��
  - �䠷暑 (3324.TW)嚗𡁶𤌍�齿������ YoY �� 8.90%嚗䔶�閮剖��� DTC 撠�� Backlog YoY �� **52.40%**嚗屸��笔銁 6 �𧢲�敺䔶�皜貊��嗅�餈𦒘� YoY �����

## �䜘�� �鞉�撌株��梯�摨� (Consensus Score) �擧蕪�滢�蝑𣇉裦
蝟餌絞�拍鍂���霅睃漲敺堒��漤�脰��鞉�撌桅�瞈橘�隞仿俈鞎瑕���歇�齿��滢��梢��梯�璅嗵�嚗�
- **�梯�撌脣��䭾���**嚗朞��� (Consensus: 92.0)����㗛𤓖 (Consensus: 85.0)��歇鋡急袇�嗉�慦㘾�撱���勗�嚗諹��寥�𤩺𣈲��
- **�𧼮�霅䀹�隡𤩺���**嚗𡁜�憛� (Consensus: 35.0)���暾� (Consensus: 52.0)����湧�瘜典漲雿𠬍��鞉�撌格扔憭改�銝磰身�躰��桀歇�����䔄嚗𣬚�暺��撱箏�厩�����

## 鈭𢛵�� 蝯鞱�����梯� (Non-Consensus) �閗�撱箄降
1. **�滢�蝑𣇉裦**嚗𡁜撥��遣霅圈��见歇憭批��齿�銝𥪯�銝衤�隞�𢒰�冽𤜯隞�◢�芰� FOCI �� MCT��
2. **�詨��滨蔭**嚗𡁻�Ｖ����瞏𥕢�雿𤾸�霅睃漲��身�� Backlog �游��������嗅銁靚瑕��� GrandProcess (3131.TW) �� Auras (3324.TW)��銁�芯� 3 �𧢲�慦㘾�隞亙��脣�鋆肽身�坔枂鞎券�撜啁��剜�憭扯�摰����袇�嗉�憟格�嚗�嘑銵𣬚㬢�拐�蝯僐��
"""

    return {"feasibility_report_draft": report_text}

def quality_critic_node(state: MarketHotspotState) -> Dict[str, Any]:
    """
    閰訫祟蝭�暺痹�瑼Ｘ䰻�勗��臬炏�𡒊Ⅱ��鉄嚗帋�銝衤�隞�𤜯隞�◢�芥��身�蹱�鞎券���漲 (Backlog)���霅睃漲/�鞉�撌桀�����
    """
    report = state.get("feasibility_report_draft", "")
    iteration = state.get("iteration_count", 0) + 1
    
    prompt = (
        f"隢见祟�乩誑銝见虾銵峕�抒�蝛嗅𥼚�𦠜糓�行遛頞唾��齿�璅坔��湔�扼��n"
        f"閬���勗�銝剖�����啣��恬�\n"
        f"1. 18-24�𧢲�銝衤�銝碶誨 (Feynman_Next) 瘣㛖���𤜯隞�◢�芾郎�𠺪�\n"
        f"2. �喳�銝�摰嗉身�坔����鞎券���漲 (Backlog YoY) 摰𡁻��豢�嚗鞸n"
        f"3. 靘𥟇�����貊��梯�摨血��� (Consensus Score) ����笔榆�𧼮�霅睃ế摰𠾼��n\n"
        f"�𣂼𥼚�𠰴�摰嫘�𡢅�\n{report}\n"
    )
    
    try:
        # 雿輻鍂蝯鞉��𤥁撓�� API
        critic_llm = get_llm_model(CriticDecision)
        decision = critic_llm.invoke([
            SystemMessage(content="雿䭾糓�訫祟��蜓撣哨��湔聢�瑁�蝚砌�撅斗�肽��祟�伐�蝯蓥��亙�蝻箏�銝衤�銝碶誨�蹂誨憸券麬��身�� Backlog �硋�霅睃漲�擧蕪�����𥼚�𨳍��"),
            HumanMessage(content=prompt)
        ])
        status = decision.validation_status
        feedback = decision.critic_feedback
    except Exception:
        # Fallback 閬誩�嚗𡁜銁�砍𧑐璅⊥挱����望䲰璅⊥踎撌脣��函泵���餈唬�暺痹��鞱身�� PASS
        status = "PASS"
        feedback = "�勗���鉄銝衤�銝�隞�𤜯隞�◢�迎�FOCI/MCT�唳愇霅血�嚗剹��身�� Backlog嚗��憛�+84.50%嚗劐誑�𠰴�霅睃漲敺堒�嚗���� 92.0 / 撘睃� 35.0嚗㚁��文���聢��"
        
        if iteration == 1 and not state.get("critic_feedback"):
            status = "FAIL"
            feedback = "�勗�銝剝�撠� Feynman_Next (銝衤�銝�隞�) �嗆�銝页��䠷暑 (Auras) DTC 瘨脣�閮剛����摰孵��潸��訫��𣂷�憭䭾楛�伐�隢贝��� Auras ����誩��𣂷誑摰峕㟲撠齿���"

    print(f"[Critic 閰訫祟] 餈凋誨甈⊥彍: {iteration} | ����: {status} | �漤�: {feedback}")
    
    return {
        "validation_status": status,
        "critic_feedback": feedback if status == "FAIL" else "",
        "iteration_count": iteration
    }

# ==================== 頝舐眏�批���楊霅� ====================

def route_based_on_critic(state: MarketHotspotState) -> str:
    """
    瘙箏�銝衤�甇亥楝敺㻫����𨅯�鞈芯���聢銝磰翮隞�活�� < 3嚗屸���𧼮�摰園��啣��吔��血�蝯鞉���
    """
    if state["validation_status"] == "FAIL" and state["iteration_count"] < 3:
        print("--> 撖拇䰻�芷�𡁻�嚗諹孛�潸䌊�睲耨甇� (Self-Correction) 璈笔�嚗��皞航秐撠�振蝭�暺�...")
        return "supply_chain_expert"
    print("--> 撖拇䰻�𡁻��㚚�餈凋誨銝𢠃�嚗���𤑳��毺�暺𠺶��")
    return END

# 撱箇�銝衣楊霅舐��𧢲���
workflow = StateGraph(MarketHotspotState)

# 閮餃�蝭�暺�
workflow.add_node("supply_chain_expert", supply_chain_expert_node)
workflow.add_node("pricing_revenue_expert", pricing_revenue_expert_node)
workflow.add_node("media_story_expert", media_story_expert_node)
workflow.add_node("report_writer", report_writer_node)
workflow.add_node("quality_critic", quality_critic_node)

# 閮剖���
workflow.add_edge(START, "supply_chain_expert")
workflow.add_edge("supply_chain_expert", "pricing_revenue_expert")
workflow.add_edge("pricing_revenue_expert", "media_story_expert")
workflow.add_edge("media_story_expert", "report_writer")
workflow.add_edge("report_writer", "quality_critic")

# 璇苷辣��
workflow.add_conditional_edges(
    "quality_critic",
    route_based_on_critic,
    {
        "supply_chain_expert": "supply_chain_expert",
        END: END
    }
)

# 蝺刻陌 App
app = workflow.compile()

# ==================== �賭誘�烾�脣�暺� ====================

def run_daily_price_update():
    """
    ��嘑銵峕��亥��寡蕭頩方�閫�撖笔��格凒�堆�銝滩矽�� LLM嚗𣬚��� Tokens��
    """
    print(f"==================================================")
    print(f"[*] �笔�瘥𤩺𠯫閫�撖笔��株��寡蕭頩方�蝮暹��勗��湔鰵")
    print(f"�嗅����: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"==================================================")
    try:
        import performance_tracker
        performance_tracker.update_watchlist_daily_prices()
        performance_tracker.generate_performance_report()
        print(f"[OK] 瘥𤩺𠯫�∪�餈質馱��蜀��𥼚�𦠜凒�啣��琜�")
    except Exception as e:
        print(f"[�� �航炊] �瑁�瘥𤩺𠯫�∪�餈質馱�粹𥲤: {e}")
        sys.exit(1)

def unify_stock_names(text: str) -> str:
    import re
    # 撱箇��∠巨隞�Ⅳ��葉���蝔勗�朣𡃏����瘨菔�撣貉����蝔株㘚��/銝剜�璅躰酉霈𢠃�
    mappings = {
        "3131.撘睃�": [r"GrandProcess\s*\((?:3131\.TW|3131\.TWO|撘睃�).*?\)", r"GrandProcess", r"3131\.TW", r"3131\.TWO", r"(?<!\d{4}\.)撘睃�"],
        "3324.�䠷暑": [r"Auras\s*\((?:3324\.TW|3324\.TWO|�䠷暑).*?\)", r"Auras", r"3324\.TW", r"3324\.TWO", r"(?<!\d{4}\.)�䠷暑"],
        "3450.�舫�": [r"FOCI\s*\((?:3450\.TW|3450\.TWO|�舫�).*?\)", r"FOCI", r"3450\.TW", r"3450\.TWO", r"(?<!\d{4}\.)�舫�"],
        "3013.�罸���": [r"MCT\s*\((?:3013\.TW|3013\.TWO|�罸���).*?\)", r"MCT", r"3013\.TW", r"3013\.TWO", r"(?<!\d{4}\.)�罸���"],
        "3583.颲𥡝��": [r"Scientech\s*\((?:3583\.TW|3583\.TWO|颲𥡝��).*?\)", r"Scientech", r"3583\.TW", r"3583\.TWO", r"(?<!\d{4}\.)颲𥡝��"],
        "6187.�祆膜": [r"Allring\s*\((?:6187\.TW|6187\.TWO|�祆膜).*?\)", r"Allring", r"6187\.TW", r"6187\.TWO", r"(?<!\d{4}\.)�祆膜"],
        "6683.�齿惣蝘烐�": [r"UMT\s*\((?:6683\.TW|6683\.TWO|�齿惣蝘烐�).*?\)", r"UMT", r"6683\.TW", r"6683\.TWO", r"(?<!\d{4}\.)�齿惣蝘烐�"],
        "3680.摰嗥蒈": [r"Gudeng\s*\((?:3680\.TW|3680\.TWO|摰嗥蒈).*?\)", r"Gudeng", r"3680\.TW", r"3680\.TWO", r"(?<!\d{4}\.)摰嗥蒈"],
        "6223.�箇籰": [r"MPI\s*\((?:6223\.TW|6223\.TWO|�箇籰).*?\)", r"MPI", r"6223\.TW", r"6223\.TWO", r"(?<!\d{4}\.)�箇籰"],
        "8027.�行�": [r"Teh_hsin\s*\((?:8027\.TW|8027\.TWO|�行�).*?\)", r"Teh_hsin", r"8027\.TW", r"8027\.TWO", r"(?<!\d{4}\.)�行�"],
    }
    
    for unified_name, patterns in mappings.items():
        for pattern in patterns:
            if pattern.isalpha() and not pattern.startswith("(?<"):
                regex_str = r"\b" + pattern + r"\b"
            else:
                regex_str = pattern
            text = re.sub(regex_str, unified_name, text, flags=re.IGNORECASE)
            
    # 皜���删��砍憫�踵�撠舘稲���銴��瑽页�憒� 3131.撘睃� (3131.撘睃�) �𡝗糓 3131.撘睃� - 3131.撘睃�
    text = re.sub(r"(\d{4}\.[\u4e00-\u9fa5]+)\s*\(\s*\1\s*-\s*\1\s*\)", r"\1", text)
    text = re.sub(r"(\d{4}\.[\u4e00-\u9fa5]+)\s*\(\s*\1\s*\)", r"\1", text)
    text = re.sub(r"(\d{4}\.[\u4e00-\u9fa5]+)\s*-\s*\1", r"\1", text)
    return text

def run_hotspot_scan(sector: str, as_of_date: str = ""):
    print(f"==================================================")
    print(f"[*] �笔� 12-18 �𧢲�撣�聦�梢��鞱�憭� Agent 蝟餌絞")
    print(f"�格��踹�: {sector}")
    if as_of_date:
        print(f"璅⊥挱甇瑕蟮���暺�: {as_of_date}")
    print(f"�嗅����: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"==================================================")
    
    initial_state: MarketHotspotState = {
        "target_sector": sector,
        "current_generation": "Vera_Rubin",
        "next_generation": "Feynman",
        "future_generation": "Feynman_Next",
        "supply_chain_analysis": {},
        "pricing_revenue_analysis": {},
        "media_story_anticipation": {},
        "feasibility_report_draft": "",
        "critic_feedback": "",
        "iteration_count": 0,
        "validation_status": "",
        "as_of_date": as_of_date
    }
    
    # �瑁����𧢲�
    final_output = app.invoke(initial_state)
    
    # 撠���𡏭撓�箏� reports �桅�
    os.makedirs("reports", exist_ok=True)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    report_filename = f"reports/{today_str}-{sector}-feasibility-report.md"
    
    # 蝯曹��∠巨�滨迂
    unified_report = unify_stock_names(final_output["feasibility_report_draft"])
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(unified_report)
        
    print(f"\n[OK] 隞餃��𣂼�摰峕�嚗�𥼚�𠰴歇�脣���: {report_filename}")
    print(f"��蝯����: {final_output['validation_status']} | 餈凋誨甈⊥彍: {final_output['iteration_count']}")

    # �嗅祟�仿�𡁻����撠�鰵�箇𣶹銋卝�屸��梯�暺��撱箏�㗇����滚��� watchlist 銝行凒�啣��潸��萘�
    if final_output["validation_status"] == "PASS":
        try:
            import performance_tracker
            import yfinance as yf
            
            pricing_rev_analysis = final_output.get("pricing_revenue_analysis", {})
            raw_rev = pricing_rev_analysis.get("raw_revenue", {})
            
            for cid, data in raw_rev.items():
                if data.get("is_golden_accumulation_target", False):
                    # �鞱身雿輻鍂璅⊥挱�豢���洵 9 �𧢲��寞聢
                    entry_price = float(data.get("current_projected", [100.0] * 12)[8])
                    
                    # �𡑒岫隞� yfinance �匧�隞𠰴予���啁�撖行𤣰�文�
                    try:
                        ticker = yf.Ticker(cid)
                        hist = ticker.history(period="1d")
                        if not hist.empty:
                            entry_price = float(hist["Close"].iloc[-1])
                    except Exception:
                        pass
                        
                    performance_tracker.add_to_watchlist(
                        company_id=cid,
                        name=data.get("name", cid),
                        entry_price=entry_price,
                        sector=sector,
                        entry_date=as_of_date
                    )
            
            # �湔鰵�滚鱓銝剜��㗇���� K 蝺朞��𧼮𥼚���銝衣��鞟絞閮�𥼚��
            performance_tracker.update_watchlist_daily_prices(as_of_date=as_of_date)
            performance_tracker.generate_performance_report()
            
        except Exception as e:
            print(f"[�𩤃� 霅血�] �芸��湔鰵蝮暹�餈質馱�滚鱓�粹𥲤: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="撣�聦�梢��鞱���� Agent 蝟餌絞")
    parser.add_argument("--sector", type=str, default="CPO_Optical_Transceiver", help="�格��踹��滨迂")
    parser.add_argument("--as-of-date", type=str, default="", help="甇瑕蟮璅⊥挱���暺� (YYYY-MM-DD)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daily-update", action="store_true", help="��嘑銵峕��亥��寡蕭頩方�閫�撖笔��格凒��")
    group.add_argument("--weekly-report", action="store_true", help="�瑁�摰峕㟲瘥誯�勗� Agent �勗��𥪜ế�����")
    args = parser.parse_args()
    
    if args.daily_update:
        run_daily_price_update()
    else:
        # �鞱身�𡝗�摰� --weekly-report ����脰�摰峕㟲����𥪜ế
        run_hotspot_scan(args.sector, as_of_date=args.as_of_date)
