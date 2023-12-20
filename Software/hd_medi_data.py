import re
import json
import pandas as pd
import argparse
import os
from pathlib import Path

default_keywords = {
    "forbid": ["투여하지 말 것", "경고", "금기사항", "복용하지 말 것", "복용하지 마십시오", "복용(사용)하지 말 것", "투여하지 마십시오", "하지 말 것", "즉각 중지", "중지"],
    "warning": ["신중히 투여할 것", "주의사항", "주의", "신중하게 투여할 것", "신중투여 할 것", "와 상의할 것", "주의할 사항"],
    "child": ['소아', '아이', '[0-9]+세 이하', '영유아', '신생아', '유아', '어린이', '미취학 아동', '학령기 아동', 
            '첫해', '개월령', '생후 [0-9]+개월', '생후 [0-9]+일', '초등학생', '유치원생', 
            '청소년', '학령 전 아동', '청소년기', '사춘기', '성장기', '영아'],
    "pregnant": ["임신중의","수유중의","임부","임신하고 있을 가능성","수유부","모유","여성","가임기",],
    "elderly": ['고령자', '[0-9]+세 이상']
}

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
    

def make_df(medicine_dictionary: dict, 
            forbid_keywords:list = default_keywords['forbid'], 
            warning_keywords:list = default_keywords['warning'], 
            child_keywords:list = default_keywords['child'],
            pregnancy_keywords:list = default_keywords['pregnant'], 
            elderly_keywords:list = default_keywords['elderly']) -> pd.DataFrame:
    """
    Description: Tags medicine guidelines and precautions based on topic and importance.

    Details: Second step in analyzing medicine guidelines and precautions data. Based on predesignated keyword lists, 
    tags the section headings and content with topic tags and importance tags. Returns a pandas dataframe.

    :param medicine_dictionary: Guidelines and Precautions text data in a dictionary.
    :type medicine_dictonary: dict (required)
    :param forbid_keywords: Keywords for forbidden action detection.
    :type forbid_keywords: list (optional)
    :param warning_keywords: Keywords for warned action detection.
    :type warning_keywords: list (optional)
    :param child_keywords: Keywords related to children.
    :type child_keywords: list (optional)
    :param pregnancy_keywords: Keywords related to pregnancy.
    :type pregnancy_keywords: list (optional)
    :param elderly_keywords: Keywords related to elderly.
    :type elderly_keywords: list (optional)

    :return df: Dataframe of guidelines and precautions text data, tagged section by section. 
        Columns:
            Section(str): Highest level headings
            Content(str): Actual Guidelines and Precautions text
            Section Importance(int): Tag of importance; (0: Forbidden action, 1: Warned action, 2: Useful information)
            Topics(list[int]): Tag of topic; (1: children, 2: pregnancy, 3: elderly)
    :type pandas.DataFrame

    """
    rows = []
    numbering_pattern = re.compile(r'^\d+[.)]\s*')

    for section_title, content in medicine_dictionary.items():
        section_title_str = section_title if isinstance(section_title, str) else ""
        section_title_str = re.sub(numbering_pattern, '', section_title_str)
        section_importance = tag_importance(section_title_str, forbid_keywords, warning_keywords)
        topic_tags = []
        topic_tags.append(tag_topic(section_title_str, child_keywords, 1))
        topic_tags.append(tag_topic(section_title_str, pregnancy_keywords, 2))
        topic_tags.append(tag_topic(section_title_str, elderly_keywords, 3))
        if isinstance(content, list):
            for sub in content:
                sub_topic_tags = []
                sub = re.sub(numbering_pattern, '', sub)
                if 1 not in topic_tags:
                    sub_topic_tags.append(tag_topic(sub, child_keywords, 1))
                if 2 not in topic_tags:
                    sub_topic_tags.append(tag_topic(sub, pregnancy_keywords, 2))
                if 3 not in topic_tags:
                    sub_topic_tags.append(tag_topic(sub, elderly_keywords, 3))
                sub_topic_tags = topic_tags.extend(sub_topic_tags)
                rows.append({'Section': section_title_str, 'Content': sub, 'Section Importance': section_importance, 'Topics': sub_topic_tags})
        elif isinstance(content, str):
            c_topic_tags = []
            content = re.sub(numbering_pattern, '', content)
            if 1 not in topic_tags:
                c_topic_tags.append(tag_topic(content, child_keywords, 1))
            if 2 not in topic_tags:
                c_topic_tags.append(tag_topic(content, pregnancy_keywords, 2))
            if 3 not in topic_tags:
                c_topic_tags.append(tag_topic(content, elderly_keywords, 3))
            c_topic_tags = topic_tags.extend(c_topic_tags)
            rows.append({'Section': section_title_str, 'Content': content, 'Section Importance': section_importance, 'Topics': c_topic_tags})

    df = pd.DataFrame(rows)
    return df



def main(args):
    # Use the provided path or set the default to the current working directory
    current_path = Path(args.path) or Path(os.getcwd())

    with open(current_path / "keywords_ybigta.json", 'r', encoding='utf-8') as json_file:
        keywords = json.load(json_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    # Define the command-line argument for the path
    parser.add_argument('--path', help='Specify the path to work with (default: current working directory)')

    # Parse the command-line arguments
    args = parser.parse_args()

    # Call the main function with the parsed arguments
    main(args)
