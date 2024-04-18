import os
from explain import explain_main
import torch
import numpy as np
from gnn.model import get_gnnNets
from train_gnn import TrainModel
from gendata import get_dataset
from utils.parser_utils import (
    arg_parse,
    create_args_group,
    fix_random_seed,
    get_data_args,
    get_graph_size_args,
)
from pathlib import Path
import yaml
import torch_scatter


def main(args, args_group):
    fix_random_seed(args.seed)


    # Check Torch version
    print(f"Torch version: {torch.__version__}")

    # Check Torch Scatter version
    print(f"Torch Scatter version: {torch_scatter.__version__}")

    # Check CUDA availability and version
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(torch.cuda.get_device_name(0))  # Get the name of the GPU device

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print('device:', device)

    dataset_params = args_group["dataset_params"]
    model_params = args_group["model_params"]

    dataset = get_dataset(
        dataset_root=args.data_save_dir,
        **dataset_params,
    )
    dataset.data.x = dataset.data.x.float()
    dataset.data.y = dataset.data.y.squeeze().long()
    args = get_data_args(dataset, args)
    model_params["edge_dim"] = args.edge_dim

    # For GraphCFE
    # GraphCFE Counterfactual labels
    data_y = dataset.data.y.cpu().numpy()
    if args.num_classes == 2:
        y_cf_all = 1 - data_y
    else:
        y_cf_all = []
        for y in data_y:
            y_cf_all.append(y+1 if y < args.num_classes - 1 else 0)
    args.y_cf_all = torch.FloatTensor(y_cf_all).to(device)
    # GraphCFE max num nodes
    if len(dataset) > 1:
        dataset_params["max_num_nodes"] = max([d.num_nodes for d in dataset])
    else:
        dataset_params["max_num_nodes"] = dataset.data.num_nodes
    args.max_num_nodes = dataset_params["max_num_nodes"]


    # Statistics of the dataset
    # Number of graphs, number of node features, number of edge features, average number of nodes, average number of edges
    info = {'num_graphs': len(dataset), 
    'num_nf': args.num_node_features, 
    'num_ef':args.edge_dim, 
    'avg_num_nodes': np.mean([data.num_nodes for data in dataset]), 
    'avg_num_edges': np.mean([data.edge_index.shape[1] for data in dataset]),
    #'avg_degree': np.mean([degree(data.edge_index[0]).mean().item() for data in dataset]),
    'num_classes': args.num_classes,}
    print(info)

    args.data_split_ratio = [args.train_ratio, args.val_ratio, args.test_ratio]
    dataloader_params = {
        "batch_size": args.batch_size,
        "random_split_flag": eval(args.random_split_flag),
        "data_split_ratio": args.data_split_ratio,
        "seed": args.seed,
    }

    model = get_gnnNets(args.num_node_features, args.num_classes, model_params, args.task)

    
    trainer = TrainModel(
        model=model,
        dataset=dataset,
        device=device,
        task=args.task,
        task_target = args.task_target,
        save_dir=os.path.join(args.model_save_dir, args.dataset_name, args.task_target),
        save_name=f"{args.model_name}_{args.task}_{args.num_layers}l_{args.hidden_dim}h",
        dataloader_params=dataloader_params,
    )
    if Path(os.path.join(trainer.save_dir, f"{trainer.save_name}_best.pth")).is_file():
        trainer.load_model()
    else:
        trainer.train(
            train_params=args_group["train_params"],
            optimizer_params=args_group["optimizer_params"],
        )
    # test model
    if args.task == "regression":
        _, _, _ = trainer.test()
    else:
        _, _, _, _, _ = trainer.test()

    explain_main(dataset, trainer.model, device, args)


if __name__ == "__main__":
    parser, args = arg_parse()
    args = get_graph_size_args(args)
    print('args:', args)
    # Get the absolute path to the parent directory of the current file
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    # Load the config file
    config_path = os.path.join(parent_dir, "config", "dataset.yaml")
    # read the configuration file
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    # loop through the config and add any values to the parser as arguments
    for key, value in config[args.dataset_name].items():
        setattr(args, key, value)
    
    args_group = create_args_group(parser, args)
    main(args, args_group)

