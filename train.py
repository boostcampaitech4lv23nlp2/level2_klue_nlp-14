import torch
from transformers import AutoTokenizer, AutoConfig, AutoModelForSequenceClassification

from tqdm import tqdm
import wandb

from Metric import compute_loss, compute_metrics
from load_data import RE_Dataset
import utils

from typing import Dict
import warnings

warnings.filterwarnings(action="ignore")


def train(config: Dict) -> str:
    """
    입력된 config에 따라서 모델 학습을 진행한다.
    학습 동안 가장 낮은 loss를 기록한 모델을 저장한다.

    Parameters
    ----------
    config : Dict
        config Dictionary
        "wandb":
            wandb logging check: true/false,
        "wandb_key":
            "<YOUR wandb API KEY>",
        "inference":
            학습완료 후 inference 진행 check: true/false,
        "train_data_path": "<train data path>",
        "val_data_path": "<val data path>",
        "test_data_path": "<test data path>",
        "model_name": "<pre-trained model name>",
        "epoch": number of epoch,
        "batch_size": number of batch_size,
        "lr": learning rate

    Returns
    -------
    str
        저장된 모델 경로
    """
    tokenizer = AutoTokenizer.from_pretrained(config["model_name"])

    train_dataset = RE_Dataset(config["train_data_path"], tokenizer)
    train_dataloader = torch.utils.data.DataLoader(
        train_dataset, batch_size=config["batch_size"], shuffle=False
    )

    val_dataset = RE_Dataset(config["val_data_path"], tokenizer)
    val_dataloader = torch.utils.data.DataLoader(
        val_dataset, batch_size=config["batch_size"], shuffle=False
    )

    model_config = AutoConfig.from_pretrained(config["model_name"])
    model_config.num_labels = 30
    model = AutoModelForSequenceClassification.from_pretrained(
        config["model_name"], config=model_config
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=config["lr"])

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # wandb setting
    project = config["model_name"].replace("/", "-")

    if config["wandb"]:
        wandb.login(key=config["wandb_key"])
        entity = "nlp02"
        wandb.init(
            entity=entity,
            project=project,
            name=f"(batch:{config['batch_size']},epoch:{config['epoch']},lr:{config['lr']})",
        )
        wandb.watch(model, log_freq=100)

    ##training
    lowest_valid_loss = 9999.0

    model.to(device)

    for epoch_num in range(config["epoch"]):
        model.train()
        epoch_loss = []
        with tqdm(train_dataloader, unit="batch") as tepoch:
            for i, (item, labels) in enumerate(tepoch):
                tepoch.set_description(f"Epoch {epoch_num}")

                optimizer.zero_grad()

                batch = {k: v.to(device) for k, v in item.items()}
                pred = model(**batch).logits
                loss = compute_loss(pred, labels.to(device))
                epoch_loss.append(loss)

                loss.backward()
                optimizer.step()

                tepoch.set_postfix(loss=loss.item())

                if config["wandb"]:
                    wandb.log({"train_loss": loss.item()})

            print(
                f"epoch: {epoch_num} train loss: {float(sum(epoch_loss) / len(epoch_loss))}"
            )

        val_loss = []
        val_pred = []
        val_labels = []
        model.eval()
        with torch.no_grad():
            for i, (item, labels) in enumerate(tqdm(val_dataloader, desc="Eval")):
                batch = {k: v.to(device) for k, v in item.items()}
                pred = model(**batch).logits
                val_pred.append(pred)
                val_labels.append(labels)

                loss = compute_loss(pred, labels.to(device))
                val_loss.append(loss)

        val_pred = torch.cat(val_pred, dim=0).detach().cpu().numpy()
        val_labels = torch.cat(val_labels, dim=0).detach().cpu().numpy()

        metrics = compute_metrics(val_pred, val_labels)
        print(metrics)

        val_loss = float(sum(val_loss) / len(val_loss))
        print(f"epoch: {epoch_num} val loss: {val_loss}")

        if config["wandb"]:
            wandb.log({"eval_loss": float(sum(epoch_loss) / len(epoch_loss))})
            wandb.log({"eval_f1": metrics["micro f1 score"]})
            wandb.log({"eval_auprc": metrics["auprc"]})
            wandb.log({"eval_accuracy": metrics["accuracy"]})

        if lowest_valid_loss > val_loss:
            save_model_dir = f"./best_model/{project}"
            if utils.create_directory(save_model_dir):
                save_model_path = f"{save_model_dir}/{project}_b{config['batch_size']}_e{config['epoch']}_lr{config['lr']}.bin"
                print(
                    "Acc for model which have lower valid loss: ", metrics["accuracy"]
                )
                torch.save(
                    model.state_dict(),
                    save_model_path,
                )
                lowest_valid_loss = val_loss

    print("---- Train Finish! ----")
    return save_model_path

from sklearn.model_selection import KFold

def trainKFold(config: dict) -> str:
    """
    입력된 config에 따라서 모델 학습을 진행한다.
    학습 동안 가장 낮은 loss를 기록한 모델을 저장한다.

    Parameters
    ----------
    config : dict
        config Dictionary
        "wandb":
            wandb logging check: true/false,
        "wandb_key":
            "<YOUR wandb API KEY>",
        "inference":
            학습완료 후 inference 진행 check: true/false,
        "train_data_path": "<train data path>",
        "val_data_path": "<val data path>",
        "test_data_path": "<test data path>",
        "model_name": "<pre-trained model name>",
        "epoch": number of epoch,
        "batch_size": number of batch_size,
        "lr": learning rate
        "k-fold":
            k-fold 적용 여부 check: true/false,
        "k-fold_config":{
            "num_splits": number of folds,
            "split_seed": random seed value,
            "shuffle":
                
        }

    Returns
    -------
    str
        저장된 모델 경로
    """
    tokenizer = AutoTokenizer.from_pretrained(config["model_name"])

    kfold_config=config["k-fold_config"]
    total_dataset = RE_Dataset(config["train_data_path"], tokenizer)

    # 데이터셋 num_splits 번 fold
    if kfold_config["shuffle"]:
        kf = KFold(n_splits=kfold_config["num_splits"], shuffle=True, random_state=kfold_config["split_seed"])
    else:
        kf = KFold(n_splits=kfold_config["num_splits"], shuffle=False)

    for fold,(train_idx,val_idx) in enumerate(kf.split(total_dataset)):
        print('------------fold no---------{}----------------------'.format(fold))
        train_subsampler = torch.utils.data.SubsetRandomSampler(train_idx)
        val_subsampler = torch.utils.data.SubsetRandomSampler(val_idx)

        train_dataloader = torch.utils.data.DataLoader(
            total_dataset, 
            batch_size=config["batch_size"], 
            shuffle=False,
            sampler=train_subsampler
        )

        val_dataloader = torch.utils.data.DataLoader(
            total_dataset, 
            batch_size=config["batch_size"], 
            shuffle=False,
            sampler=val_subsampler
        )

        model_config = AutoConfig.from_pretrained(config["model_name"])
        model_config.num_labels = 30

        model = AutoModelForSequenceClassification.from_pretrained(
            config["model_name"], config=model_config
        )

        optimizer = torch.optim.Adam(model.parameters(), lr=config["lr"])

        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

        # wandb setting
        project = config["model_name"].replace("/", "-")

        if config["wandb"]:
            wandb.login(key=config["wandb_key"])
            entity = "nlp02"
            wandb.init(
                entity=entity,
                project=project,
                name=f"(fold:{fold},batch:{config['batch_size']},epoch:{config['epoch']},lr:{config['lr']})",
            )
            wandb.watch(model, log_freq=100)

        ##training
        lowest_valid_loss = 9999.0

        model.to(device)

        for epoch_num in range(config["epoch"]):
            model.train()
            epoch_loss = []
            with tqdm(train_dataloader, unit="batch") as tepoch:
                for i, (item, labels) in enumerate(tepoch):
                    tepoch.set_description(f"Epoch {epoch_num}")

                    optimizer.zero_grad()

                    batch = {k: v.to(device) for k, v in item.items()}
                    pred = model(**batch).logits
                    loss = compute_loss(pred, labels.to(device))
                    epoch_loss.append(loss)

                    loss.backward()
                    optimizer.step()

                    tepoch.set_postfix(loss=loss.item())

                    if config["wandb"]:
                        wandb.log({"train_loss": loss.item()})

                print(
                    f"epoch: {epoch_num} train loss: {float(sum(epoch_loss) / len(epoch_loss))}"
                )

            val_loss = []
            val_pred = []
            val_labels = []
            model.eval()
            with torch.no_grad():
                for i, (item, labels) in enumerate(tqdm(val_dataloader, desc="Eval")):
                    batch = {k: v.to(device) for k, v in item.items()}
                    pred = model(**batch).logits
                    val_pred.append(pred)
                    val_labels.append(labels)

                    loss = compute_loss(pred, labels.to(device))
                    val_loss.append(loss)

            val_pred = torch.cat(val_pred, dim=0).detach().cpu().numpy()
            val_labels = torch.cat(val_labels, dim=0).detach().cpu().numpy()

            metrics = compute_metrics(val_pred, val_labels)
            print(metrics)

            val_loss = float(sum(val_loss) / len(val_loss))
            print(f"epoch: {epoch_num} val loss: {val_loss}")

            if config["wandb"]:
                wandb.log({"eval_loss": float(sum(epoch_loss) / len(epoch_loss))})
                wandb.log({"eval_f1": metrics["micro f1 score"]})
                wandb.log({"eval_auprc": metrics["auprc"]})
                wandb.log({"eval_accuracy": metrics["accuracy"]})

            if lowest_valid_loss > val_loss:
                save_model_path = f"best_model/{project}/{fold}/{project}_b{config['batch_size']}_e{config['epoch']}_lr{config['lr']}.bin"
                print("Acc for model which have lower valid loss: ", metrics["accuracy"])
                torch.save(
                    model.state_dict(),
                    save_model_path,
                )
                lowest_valid_loss = val_loss

    print("---- Train Finish! ----")
    return save_model_path


if __name__ == "__main__":
    import json

    with open("config.json", "r") as f:
        train_config = json.load(f)
    if train_config["k-fold"]:
        trainKFold(train_config)
    else:
        train(train_config)
