import pickle as pickle

import torch
from torch.utils.data import DataLoader
import torch.nn.functional as F

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
)

import pandas as pd
import numpy as np
from tqdm import tqdm

import load_data
import utils

from typing import Tuple, List, Dict


def inference(model, tokenized_sent, device) -> Tuple[List, List]:
    """
    test dataset을 DataLoader로 만들어 준 후,
    batch_size로 나눠 model이 예측 합니다.

    Parameters
    ----------
    model :
        예측에 사용할 모델
    tokenized_sent : _type_
        tokenized 된 Dataset 객체
    device :
        모델이 올라가는 divice(cude/cpu)

    Returns
    -------
    Tuple[list, list]
        예측 문자열 라벨 리스트
        라벨 별 예측 확률 리스트 of 리스트
    """
    dataloader = DataLoader(tokenized_sent, batch_size=16, shuffle=False)
    model.eval()
    output_pred = []
    output_prob = []
    for i, (data, labels) in enumerate(tqdm(dataloader)):
        with torch.no_grad():
            outputs = model(
                input_ids=data["input_ids"].to(device),
                attention_mask=data["attention_mask"].to(device),
                token_type_ids=data["token_type_ids"].to(device),
            )
        logits = outputs[0]
        prob = F.softmax(logits, dim=-1).detach().cpu().numpy()
        logits = logits.detach().cpu().numpy()
        result = np.argmax(logits, axis=-1)

        output_pred.append(result)
        output_prob.append(prob)

    return (
        np.concatenate(output_pred).tolist(),
        np.concatenate(output_prob, axis=0).tolist(),
    )


def num_to_label(label: List) -> List:
    """
    숫자로 되어 있던 class를 원본 문자열 라벨로 변환 합니다.

    Parameters
    ----------
    label : List
        숫자로 되어 있는 class List

    Returns
    -------
    List
        문자열 라벨 List
    """
    origin_label = []
    with open("dict_num_to_label.pkl", "rb") as f:
        dict_num_to_label = pickle.load(f)
    for v in label:
        origin_label.append(dict_num_to_label[v])

    return origin_label


def load_test_dataset(
    dataset_dir: str, tokenizer: AutoTokenizer
) -> Tuple[pd.Series, torch.utils.data.Dataset]:
    """
    데이터 셋을 불러와서 tokenzied된 Dataset를 만든다.

    Parameters
    ----------
    dataset_dir : str
        Dataset으로 만들 데이터 셋 경로
    tokenizer : AutoTokenizer
        데이터 셋을tokenize를 할 tokenizer

    Returns
    -------
    Tuple[pd.Series, torch.Dataset]
        inference 할 데이터 셋의 id Series
        raw 데이터 셋을 inference에 사용할 Dataset 객체
    """
    df = pd.read_csv(dataset_dir)

    Re_test_dataset = load_data.RE_Dataset(dataset_dir, tokenizer, "prediction")

    return df["id"], Re_test_dataset


def main_inference(config: Dict, model_path: str):
    """
    주어진 config와 model_path를 사용하여 모델을 inference를 한다.

    Parameters
    ----------
    config : Dict
        config Dictionary
        "wandb":
            wandb logging check: true/false,
        "wandb_key":
            "<YOUR wandb API KEY>",
        "inference":
            학습완료 후 inference 진행 check: true/false
        "train_data_path": "<train data path>",
        "val_data_path": "<val data path>",
        "test_data_path": "<test data path>",
        "model_name": "<pre-trained model name>",
        "epoch": number of epoch,
        "batch_size": number of batch_size,
        "lr": learning rate
    model_path : str
       inference를 진행할 모델 경로
    """

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    # load tokenizer
    Model_NAME = config["model_name"]
    tokenizer = AutoTokenizer.from_pretrained(Model_NAME)

    ## load my model
    model = AutoModelForSequenceClassification.from_pretrained(
        pretrained_model_name_or_path=Model_NAME, num_labels=30
    )

    model.load_state_dict(torch.load(model_path))
    # model.parameters
    model.to(device)

    ## load test datset
    test_dataset_dir = config["test_data_path"]
    test_id, Re_test_dataset = load_test_dataset(test_dataset_dir, tokenizer)

    ## predict answer
    pred_answer, output_prob = inference(
        model, Re_test_dataset, device
    )  # model에서 class 추론
    pred_answer = num_to_label(pred_answer)  # 숫자로 된 class를 원래 문자열 라벨로 변환.

    ## make csv file with predicted answer
    #########################################################
    # 아래 directory와 columns의 형태는 지켜주시기 바랍니다.
    output = pd.DataFrame(
        {
            "id": test_id,
            "pred_label": pred_answer,
            "probs": output_prob,
        }
    )

    project = Model_NAME.replace("/", "-")
    save_inference_dir = f"./prediction/{project}"
    if utils.create_directory(save_inference_dir):
        save_inference_path = f"{save_inference_dir}/{project}_b{config['batch_size']}_e{config['epoch']}_lr{config['lr']}.csv"

        print(save_inference_path)
        output.to_csv(
            save_inference_path, index=False
        )  # 최종적으로 완성된 예측한 라벨 csv 파일 형태로 저장.
        #### 필수!! ##############################################
        print("---- Inference Finish! ----")


if __name__ == "__main__":
    import json

    with open("config.json", "r") as f:
        config = json.load(f)

    # print(config)

    model_path = "/opt/ml/level2_klue_nlp-14/best_model/klue-bert-base/klue-bert-base_b128_e10_lr1e-05.bin"

    main_inference(config, model_path)
