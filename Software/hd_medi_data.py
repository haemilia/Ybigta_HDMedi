import re
import json
import pandas as pd
import argparse
import os
from pathlib import Path

def split_sections(text:str) -> dict:
    """
    Description: Transforms medicine guidelines and precautions text data into dictionary that retains the original text's hierarchy.

    Details: First step in analyzing medicine guidelines and precutions data. Divides the text into its headings and paragraph contents.
    Uses regular expressions to recognize patterns in formatting.

    :param text: Guidelines and Precautions text data for a medicine.
    :type text: str (required)

    :return structured_data: Dictionary with headings as keys and paragraph content as values
    :type dict{str: [str]}

    """
    if not isinstance(text, str):
        # A way to deal with null data values
        return {}
    
    # 섹션과 하위 섹션을 식별하기 위한 정규 표현식
    section_pattern = re.compile(r'^(\d+\.\s[^:\n]+)')
    
    # 괄호를 포함한 하위 섹션 식별을 방지하기 위한 수정
    ### \d+\): 숫자 뒤에 닫는 괄호())가 오는 패턴 (예: 1))
    ### [①-⑳]: 동그란 숫자 기호 (예: ① ~ ⑳)
    ### ^[가-힣]+\.\s.*: 한글 문자 뒤에 점(.)이 오는 패턴 (예: 가., 나., 다.)
    subsection_pattern = re.compile(r'^(\d+\)|[①-⑳])\s.*|^[가-힣]+\.\s.*')

    lines = text.split('\n')
    structured_data = {}
    current_section = None
    current_content = ""
    current_subsections = []

    for line in lines:
        section_match = section_pattern.match(line)
        subsection_match = subsection_pattern.match(line)

        if section_match:
            # 새 섹션을 시작하기 전에 이전 섹션과 하위 섹션을 저장합니다.
            if current_section:
                if current_subsections:
                    structured_data[current_section] = current_subsections
                else:
                    structured_data[current_section] = current_content.strip()
            current_section = section_match.group()
            current_content = ""
            current_subsections = []
            
        elif subsection_match and current_section:
            # 현재 섹션의 하위 섹션을 추가합니다.
            if current_content:
                current_subsections.append(current_content.strip())
            current_subsections.append(subsection_match.group())
            current_content = ""
            
        else:
            # 섹션의 내용을 추가합니다.
            current_content += "\n" + line.strip()

    # 마지막 섹션의 내용을 저장합니다.
    if current_section:
        if current_subsections:
            structured_data[current_section] = current_subsections
        else:
            structured_data[current_section] = current_content.strip()

    return structured_data


def tag_importance(section_title:str, forbid_list:list, warning_list:list)-> int:
    """
    Description: Helper Function for make_df(). 

    :param section_title: The title of the section
    :type section_title: str
    :param forbid_list: Keywords for forbidden action detection.
    :type forbid_list: list (optional)
    :param warning_list: Keywords for warned action detection.
    :type warning_list: list (optional)

    :return 
        0: forbidden action
        1: warned action
        2: useful information
    """
    if any(keyword in section_title for keyword in forbid_list):
        return 0
    elif any(keyword in section_title for keyword in warning_list):
        return 1
    else:
        return 2
    

def tag_topic(content: str, topic_keywords: list, assign_category: int) -> int:
    """
    Description: Helper function for make_df()

    :param content: the text to analyze
    :type content: str
    :param topic_keywords: list of keywords related to the topic
    :type topic_keywords: list[str]
    :param assign_category: the category tag to assign
    :type assign_category: int
    """
    if any(re.search(word, content, re.IGNORECASE) for word in topic_keywords):
        return assign_category
    else:
        return None
    

def make_df(medicine_dictionary: dict, keywords: dict ) -> (pd.DataFrame, dict):
    """
    Description: Tags medicine guidelines and precautions based on topic and importance.

    Details: Second step in analyzing medicine guidelines and precautions data. Based on predesignated keyword lists, 
    tags the section headings and content with topic tags and importance tags. Returns a pandas dataframe.

    :param medicine_dictionary: Guidelines and Precautions text data in a dictionary.
    :type medicine_dictonary: dict (required)
    :param forbid_keywords: Keywords
    :type forbid_keywords: dict (required)

    :return df: Dataframe of guidelines and precautions text data, tagged section by section. 
        Columns:
            Section(str): Highest level headings
            Content(str): Actual Guidelines and Precautions text
            Section Importance(int): Tag of importance; (0: Forbidden action, 1: Warned action, 2: Useful information)
            Topics(list[int]): Tag of topic;
    :rtype df: pandas.DataFrame
    :return topic_tag_int: Dictionary mapping topics to their topic tags
    :rtype topic_tag_int: dict

    """
    importance_keys = ["forbid", "warning"]
    importance = {key: keywords[key] for key in importance_keys if key in keywords}
    topics = {key: keywords[key] for key in keywords if key not in importance_keys}
    rows = []
    numbering_pattern = re.compile(r'^\d+[.)]\s*')
    topic_tag_int = {}
    for i, topic in enumerate(topics.keys()):
        topic_tag_int[topic] = i    

    for section_title, content in medicine_dictionary.items():
        section_title_str = section_title if isinstance(section_title, str) else ""
        section_title_str = re.sub(numbering_pattern, '', section_title_str)
        section_importance = tag_importance(section_title_str,importance["forbid"], importance["warning"])
        topic_tags = []
        
        for topic, topic_list in topics.items():
            tag = tag_topic(section_title_str, topic_list, topic_tag_int[topic])
            if tag:
                topic_tags.append(tag)

        if isinstance(content, list):
            for sub in content:
                sub_topic_tags = []
                sub = re.sub(numbering_pattern, '', sub)
                for topic, topic_list in topics.items():
                    if topic_tag_int[topic] not in topic_tags:
                        tag = tag_topic(sub, topic_list, topic_tag_int[topic])
                        if tag:
                            sub_topic_tags.append(tag)
                sub_topic_tags = topic_tags + sub_topic_tags
                rows.append({'Section': section_title_str, 'Content': sub, 'Section Importance': section_importance, 'Topics': sub_topic_tags})
        elif isinstance(content, str):
            c_topic_tags = []
            content = re.sub(numbering_pattern, '', content)
            for topic, topic_list in topics.items():
                if topic_tag_int[topic] not in topic_tags:
                    tag = tag_topic(content, topic_list, topic_tag_int[topic])
                    if tag:
                        c_topic_tags.append(tag)
            
            c_topic_tags = topic_tags + c_topic_tags
            rows.append({'Section': section_title_str, 'Content': content, 'Section Importance': section_importance, 'Topics': c_topic_tags})

    df = pd.DataFrame(rows)
    return df, topic_tag_int


disease_keywords = {
    "고혈압": ["고혈압", "혈압"],
    "저혈압": ["저혈압", "혈압"],
    "당뇨": ["당뇨", "당뇨병", "혈당", "인슐린"],
    "암": ["종양", "암", "방사선", "화학 요법"],
    "고지혈증": ["고지혈증", "콜레스테롤", "지방", "혈중 지질"],
    "갑상선": ["갑상선", "기능 항진증", "기능 저하증"],
    "비만": ["비만", "체중", "과체중", "식이"],
    "치매": ["치매", "알츠하이머", "뇌경색"],
}
def find_value_in_dict(search_value: str, search_dict:dict) -> (str, list):
    for k, v in search_dict.items():
        if search_value in v:
            return (k, v)
    return False

def process_user_input(previous_meds: list, interest_disease: list) -> (dict, dict):
    meds_dict = {}
    disease_dict = {}
    if previous_meds:
        for prev_med in previous_meds:
            meds_dict[prev_med] = [prev_med]
    else:
        meds_dict = {}
    if interest_disease:
        for disease in interest_disease:
            find_value= find_value_in_dict(disease, disease_keywords)
            if find_value:
                disease_name, disease_kw = find_value
                disease_dict[disease_name] = disease_kw
            else:
                disease_dict[disease] = [disease]
    else:
        disease_dict = {}
    return meds_dict, disease_dict         
    
def additional_tagging(in_df: pd.DataFrame, meds_dict: dict, disease_dict:dict)-> pd.DataFrame:
    meds_len = len(meds_dict)
    if meds_dict:
        meds_tag_int = {}
        for i, med in enumerate(meds_dict.keys()):
            meds_tag_int[med] = i + 5
        meds_tags = []
        for section, content in zip(in_df['Section'], in_df['Content']):
            row_meds = []
            for med, med_kw in meds_dict.items():
                section_result = tag_topic(section, med_kw, meds_tag_int[med])
                content_result = tag_topic(content, med_kw, meds_tag_int[med])
                if section_result:
                    row_meds.append(section_result)
                if content_result:
                    row_meds.append(content_result)
            meds_tags.append(row_meds)
        in_df["Past Medicine"] = meds_tags
    else:
        meds_tag_int = {}
    if disease_dict:
        disease_tag_int = {}
        for i, disease in enumerate(disease_dict.keys()):
            disease_tag_int[disease] = i + 5 + meds_len
        disease_tags = []
        for section, content in zip(in_df['Section'], in_df['Content']):
            row_disease = []
            for disease, disease_kw in disease_dict.items():
                section_result = tag_topic(section, disease_kw, disease_tag_int[disease])
                content_result = tag_topic(content, disease_kw, disease_tag_int[disease])
                if section_result:
                    row_disease.append(section_result)
                if content_result:
                    row_disease.append(content_result)
            disease_tags.append(row_disease)
        in_df["Disease Interest"] = disease_tags
    else:
        disease_tag_int = {}
    result_tag_int = {}
    result_tag_int["medicine"] = meds_tag_int
    result_tag_int["disease"] = disease_tag_int
    return in_df, result_tag_int



def main(args):
    # Use the provided path or set the default to the current working directory
    current_path = Path(args.path) or Path(os.getcwd())

    with open(current_path / "keywords_ybigta.json", 'r', encoding='utf-8') as json_file:
        default_keywords = json.load(json_file)

    med_dict = split_sections()
    med_df, topic_to_tag = make_df(med_dict, default_keywords)

    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    # Define the command-line argument for the path
    parser.add_argument('--path', help='Specify the path to work with (default: current working directory)')

    # Parse the command-line arguments
    args = parser.parse_args()

    # Call the main function with the parsed arguments
    main(args)
