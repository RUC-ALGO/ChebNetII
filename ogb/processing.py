import numpy as np
import torch
import pickle
import argparse
from ogb.nodeproppred.dataset_pyg import PygNodePropPredDataset
import scipy.sparse as sp
from torch_geometric.utils import to_undirected
from torch_sparse import SparseTensor

parser = argparse.ArgumentParser()
parser.add_argument('--data_name', type=str, default="arxiv", help='datasets.')
parser.add_argument('--K', type=int, default=10, help='propagation steps.')
args = parser.parse_args()
data_path="./data/"


def sys_normalized_adjacency(adj):
   adj = sp.coo_matrix(adj)
   row_sum = np.array(adj.sum(1))
   row_sum=(row_sum==0)*1+row_sum
   d_inv_sqrt = np.power(row_sum, -0.5).flatten()
   d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0.
   d_mat_inv_sqrt = sp.diags(d_inv_sqrt)
   return d_mat_inv_sqrt.dot(adj).dot(d_mat_inv_sqrt).tocoo()

def sparse_mx_to_torch_sparse_tensor(sparse_mx):
    """Convert a scipy sparse matrix to a torch sparse tensor."""
    sparse_mx = sparse_mx.tocoo().astype(np.float32)
    indices = torch.from_numpy(
        np.vstack((sparse_mx.row, sparse_mx.col)).astype(np.int64))
    values = torch.from_numpy(sparse_mx.data)
    shape = torch.Size(sparse_mx.shape)
    return torch.sparse.FloatTensor(indices, values, shape)

#Loading dataset
if args.data_name=="arxiv":
    dataset = PygNodePropPredDataset(name='ogbn-arxiv')
elif args.data_name=="papers100m":
    dataset = PygNodePropPredDataset(name = "ogbn-papers100M")
print("Loading completed!")

data = dataset[0]
split_idx = dataset.get_idx_split()

#get split indices
train_idx, valid_idx, test_idx = split_idx['train'], split_idx['valid'], split_idx['test']
edge_index = data.edge_index
N = data.num_nodes

#save labels
labels = data.y.data
labels_train = labels[train_idx].reshape(-1).long()
labels_valid = labels[valid_idx].reshape(-1).long()
labels_test = labels[test_idx].reshape(-1).long()
with open(data_path+"labels_"+args.data_name+".pickle","wb") as fopen:
   pickle.dump([labels_train,labels_valid,labels_test],fopen)
print("Labels have been saved!")

# to undirected
print('Making the graph undirected')
edge_index = to_undirected(edge_index)

#Load edges and create adjacency
row,col = edge_index
row=row.numpy()
col=col.numpy()
adj_mat=sp.csr_matrix((np.ones(row.shape[0]),(row,col)),shape=(N,N))

print("Get scaled laplacian matrix.")
adj_mat = sys_normalized_adjacency(adj_mat)
adj_mat = -1.0*adj_mat #\hat{L}=2/(L*lambda_max)-I, lambda_max=2, \hat{L}=L-I=-P

adj_mat = sparse_mx_to_torch_sparse_tensor(adj_mat)
list_mat_train = []
list_mat_valid = []
list_mat_test = []

#T_0(\hat{L})X
T_0_feat = data.x.numpy()
T_0_feat = torch.from_numpy(T_0_feat).float()

# del for free
del dataset, data, edge_index, row, col, labels

list_mat_train.append(T_0_feat[train_idx,:])
list_mat_valid.append(T_0_feat[valid_idx,:])
list_mat_test.append(T_0_feat[test_idx,:])

#T_1(\hat{L})X
T_1_feat = torch.spmm(adj_mat,T_0_feat)
list_mat_train.append(T_1_feat[train_idx,:])
list_mat_valid.append(T_1_feat[valid_idx,:])
list_mat_test.append(T_1_feat[test_idx,:])

# compute T_k(\hat{L})X
print("Begining of iteration!")
for i in range(1,args.K):
    #T_k(\hat{L})X
    T_2_feat = torch.spmm(adj_mat,T_1_feat)
    T_2_feat = 2*T_2_feat-T_0_feat
    T_0_feat, T_1_feat =T_1_feat, T_2_feat

    list_mat_train.append(T_2_feat[train_idx,:])
    list_mat_valid.append(T_2_feat[valid_idx,:])
    list_mat_test.append(T_2_feat[test_idx,:])
    print("Done:",i)

with open(data_path+"training_"+args.data_name+".pickle","wb") as fopen:
    pickle.dump(list_mat_train,fopen)

with open(data_path+"validation_"+args.data_name+".pickle","wb") as fopen:
    pickle.dump(list_mat_valid,fopen)

with open(data_path+"test_"+args.data_name+".pickle","wb") as fopen:
    pickle.dump(list_mat_test,fopen)

print(args.data_name+" has been successfully processed")

