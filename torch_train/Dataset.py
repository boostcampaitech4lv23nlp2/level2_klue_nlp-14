import pickle as pickle
import torch
from torch.utils.data import Dataset
import pandas as pd

class TrainDataset(Dataset):
    def __init__(self, data_path, tokenizer):
        pd_dataset = pd.read_csv(data_path)
        raw_dataset = preprocessing_dataset(pd_dataset)
        raw_labels = raw_dataset['label'].values

        self.data = tokenize_dataset(raw_dataset, tokenizer)
        self.labels = label_to_num(raw_labels)
    """
    def __getitem__(self, idx):
        item = {key: val[idx].clone().detach() for key, val in self.data.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item
    """
    def __getitem__(self, idx):
        item = {key: val[idx].clone().detach() for key, val in self.data.items()}
        labels = torch.tensor(self.labels[idx])
        return item, labels

    def __len__(self):
        return len(self.labels)

def preprocessing_dataset(dataset):
    subject_entity = []
    object_entity = []
    for i,j in zip(dataset['subject_entity'], dataset['object_entity']):
        i = i[1:-1].split(',')[0].split(':')[1]
        j = j[1:-1].split(',')[0].split(':')[1]
        subject_entity.append(i)
        object_entity.append(j)
    output_dataset = pd.DataFrame({
        'id':dataset['id'],
        'sentence':dataset['sentence'],
        'subject_entity':subject_entity,
        'object_entity':object_entity,
        'label': dataset['label']
    })
    return output_dataset

def tokenize_dataset(dataset, tokenizer):
    concat_entity = []
    for e01, e02 in zip(dataset['subject_entity'], dataset['object_entity']):
        temp = ''
        temp = e01 + '[SEP]' + e02
        concat_entity.append(temp)

    tokenized_sentences = tokenizer(
        concat_entity,
        list(dataset['sentence']),
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=256,
        add_special_tokens=True,
        )
    
    return tokenized_sentences


def label_to_num(label):
    num_label = []
    with open('dict_label_to_num.pkl', 'rb') as f:
        dict_label_to_num = pickle.load(f)
    for v in label:
        num_label.append(dict_label_to_num[v])
  
    return num_label