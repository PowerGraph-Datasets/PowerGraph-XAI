import os.path as osp
import torch
import mat73
from sklearn.model_selection import train_test_split
import os
from torch_geometric.data import InMemoryDataset, Dataset, Data, download_url, extract_zip
from torch_geometric.data import DataLoader, DenseDataLoader
import torch
import numpy as np



class PowerGrid(Dataset):
    # Base folder to download the files
    names = {
        "uk": ["uk", "Uk", "UK", None],
        "ieee24": ["ieee24", "Ieee24", "IEEE24", None],
        "ieee39": ["ieee39", "Ieee39", "IEEE39", None],
        "ieee118": ["ieee118", "Ieee118", "IEEE118", None],
        "swissgrid": ["swissgrid", "Swissgrid", "SwissGrid", "SWISSGRID"],
    }

    def __init__(self, name, root, datatype='Binary', transform=None, pre_transform=None, pre_filter=None, device = 'cpu'):
        # root - where the dataset (.pt files) should be stored, here, in ieee24 or 39 or 118 or uk folder
        # name - name of the dataset, here, ieee24 or 39 or 118 or uk
        self.datatype = datatype
        self.name = name.lower()
        self.raw_path = self.name + '+expmask' #raw path is the folder where .mat files from matlab are saved
        self.device = device

        # check if the dataset is available
        assert self.name in self.names.keys()

        super(PowerGrid, self).__init__(root, transform, pre_transform, pre_filter)

    @property
    def raw_file_names(self):
        # List of the raw files
        return ['Bf.mat',
                'blist.mat',
                'Ef.mat',
                'exp.mat',
                'of_bi.mat',
                'of_mc.mat',
                'of_reg.mat']

    @property
    def processed_file_names(self):
        # if these files are found in the processed folder, the process function is not called
        return 'data.pt'


    def len(self):
        return len(self.processed_file_names)

    def get(self, idx):
        data = torch.load(osp.join(self.processed_dir, f'data_{idx}.pt'))
        return data
    
    def download(self):
        # Download the file specified in self.url and store
        # it in self.raw_dir
        # path = self.raw_path
        pass

    def process(self):
        # function that deletes row
        def th_delete(tensor, indices):
            mask = torch.ones(tensor.size(), dtype=torch.bool)
            mask[indices] = False
            return tensor[mask]

        idx = 0
        # load branch list also called edge order or edge index
        path = os.path.join(self.raw_path, 'blist.mat')
        edge_order = mat73.loadmat(path)
        edge_order = torch.tensor(edge_order["bList"] - 1)
        # load output binary classification labels
        path = os.path.join(self.raw_path, 'of_bi.mat')
        of_bi = mat73.loadmat(path)
        # load output binary regression labels
        path = os.path.join(self.raw_path, 'of_reg.mat')
        of_reg = mat73.loadmat(path)
        # load output mc labels
        path = os.path.join(self.raw_path, 'of_mc.mat')
        of_mc = mat73.loadmat(path)
        # load output node feature matrix
        path = os.path.join(self.raw_path, 'Bf.mat')
        node_f = mat73.loadmat(path)
        # load output edge feature matrix
        path = os.path.join(self.raw_path, 'Ef.mat')
        edge_f = mat73.loadmat(path)

        path = os.path.join(self.raw_path, 'exp.mat')
        exp = mat73.loadmat(path)

        node_f = node_f['B_f_tot']
        edge_f = edge_f['E_f_post']
        of_bi = of_bi['output_features']
        of_mc = of_mc['category']
        exp_mask = exp['explainations']


        # MAIN data processing loop
        for i in range(len(node_f)):
            # node feat
            x = torch.tensor(node_f[i][0], dtype=torch.float32).reshape([-1, 3]).to(device)
            # edge feat
            f = torch.tensor(edge_f[i][0], dtype=torch.float32)
            e_mask = torch.zeros(len(edge_f[i][0]), 1)
            if exp_mask[i][0].all() == 0:
                e_mask = e_mask
            else:
                e_mask[exp_mask[i][0]] = 1
            # contigency lists, finds where do we have contigencies from the .mat edge feature matrices
            # ( if a line is part of the contigency list all egde features are set 0)
            cont = [j for j in range(len(f)) if np.all(np.array(f[j])) == 0]
            e_mask_post = th_delete(e_mask, cont)
            e_mask_post = torch.cat((e_mask_post, e_mask_post), 0).to(self.device)
            # remove edge features of the associated line
            f_tot = th_delete(f, cont).reshape([-1, 4]).type(torch.float32)
            # concat the post-contigency edge feature matrix to take into account the reversed edges
            f_totw = torch.cat((f_tot, f_tot), 0).to(self.device)
            # remove failed lines from branch list
            edge_iw = th_delete(edge_order, cont).reshape(-1, 2).type(torch.long)
            # flip branch list
            edge_iwr = torch.fliplr(edge_iw)
            #  and concat the non flipped and flipped branch list
            edge_iw = torch.cat((edge_iw, edge_iwr), 0)
            edge_iw = edge_iw.t().contiguous().to(self.device)

            data_type = self.datatype
            if data_type == 'Binary' or data_type == 'binary':
                ydata = torch.tensor(of_bi[i][0], dtype=torch.float, device=self.device).view(1, -1)
            if data_type == 'Regression' or data_type == 'regression':
                ydata = torch.tensor(of_reg[i][0], dtype=torch.int, device=self.device).view(1, -1)
            if data_type == 'Multiclass' or data_type == 'multiclass':
                #do argmax
                ydata = torch.tensor(np.argmax(of_mc[i][0]), dtype=torch.int, device=self.device).view(1, -1)

            # Fill Data object, 1 Data object -> 1 graph
            data = Data(x=x, edge_index=edge_iw, edge_attr=f_totw, y=ydata, edge_mask=e_mask_post)
            # append Data object to datalist

            if self.pre_filter is not None and not self.pre_filter(data):
                continue

            if self.pre_transform is not None:
                data = self.pre_transform(data)

            torch.save(data, osp.join(self.processed_dir, f'data_{idx}.pt')) # Have to change the name
            idx += 1


if __name__ == '__main__':
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    dataset = PowerGrid(name= 'uk', root = 'uk', datatype='multiclass', device = device)





#SBATCH --gpus=rtx_2080_ti:1
#SBATCH --gres=gpumem:8G
