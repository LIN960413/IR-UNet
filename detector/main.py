import argparse
import os
import time
import numpy as np
import data
from importlib import import_module
import shutil
from utils import *
import sys
sys.path.append('../')
from split_combine import SplitComb
# from time import time
import torch
from torch.nn import DataParallel
from torch.backends import cudnn
from torch.utils.data import DataLoader
from torch import optim
from torch.autograd import Variable
# from config_training import config as config_training

from layers import acc

parser = argparse.ArgumentParser(description='PyTorch DataBowl3 Detector')
parser.add_argument('--num_classes', default=1, type=int,
                        help='number of classes')
parser.add_argument('--model', '-m', metavar='MODEL', default='res18',
                    help='model')
parser.add_argument('--config', '-c', default='config_training', type=str)
parser.add_argument('-j', '--workers', default=0, type=int, metavar='N',
                    help='number of data loading workers (default: 0)')
parser.add_argument('--epochs', default=1, type=int, metavar='N',  #100
                    help='number of total epochs to run')
parser.add_argument('--start-epoch', default=0, type=int, metavar='N',
                    help='manual epoch number (useful on restarts)')
parser.add_argument('-b', '--batch-size', default=1, type=int,
                    metavar='N', help='mini-batch size (default: 1)')  #16
parser.add_argument('--lr', '--learning-rate', default=0.01, type=float,
                    metavar='LR', help='initial learning rate')
parser.add_argument('--momentum', default=0.9, type=float, metavar='M',
                    help='momentum')
parser.add_argument('--weight-decay', '--wd', default=1e-4, type=float,
                    metavar='W', help='weight decay (default: 1e-4)')
parser.add_argument('--save-freq', default='1', type=int, metavar='S',
                    help='save frequency')
parser.add_argument('--resume', default='', type=str, metavar='PATH',
                    help='path to latest checkpoint (default: none)')
parser.add_argument('--save-dir', default='', type=str, metavar='SAVE',
                    help='directory to save checkpoint (default: none)')
parser.add_argument('--test', default=0, type=int, metavar='TEST',
                    help='1 do test evaluation, 0 not')
parser.add_argument('--testthresh', default=-3, type=float,
                    help='threshod for get pbb')
parser.add_argument('--split', default=8, type=int, metavar='SPLIT',
                    help='In the test phase, split the image to 8 parts')
parser.add_argument('--gpu', default='-1', type=str, metavar='N',
                    help='use cpu')
parser.add_argument('--n_test', default=2, type=int, metavar='N',
                    help='number of gpu for test')

def main():
    global args

    start = time.time()
    print('start!')
    args = parser.parse_args()
    config_training = import_module(args.config)
    config_training = config_training.config
    # from config_training import config as config_training
    torch.manual_seed(0)
    torch.cuda.set_device(-1)
    model = import_module(args.model)
    config, net, loss, get_pbb = model.get_model()
    start_epoch = args.start_epoch#0
    
    save_dir = args.save_dir#res18/retrft960
    # print('args.resume!',args.resume, time() - start)
    if args.resume:
        checkpoint = torch.load(args.resume)
        print('args.resume', args.resume)
        # if start_epoch == 0:
        #     start_epoch = checkpoint['epoch'] + 1
        # if not save_dir:
        #     save_dir = checkpoint['save_dir']
        # else:
        #     save_dir = os.path.join('results',save_dir)
        net.load_state_dict(checkpoint['state_dict'])
    # else:
    # print('start_epoch',start_epoch, time() - start)
    if start_epoch == 0:
        start_epoch = 1
    if not save_dir:
        exp_id = time.strftime('%Y%m%d-%H%M%S', time.localtime())
        save_dir = os.path.join('results', args.model + '-' + exp_id)
    else:
        save_dir = os.path.join('results',save_dir)
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    logfile = os.path.join(save_dir,'log')
    # print('args.test',args.test, time() - start)
    if args.test!=1:
        sys.stdout = Logger(logfile)
        pyfiles = [f for f in os.listdir('./') if f.endswith('.py')]
        # print('pyfiles', time() - start)
        for f in pyfiles:
            shutil.copy(f,os.path.join(save_dir,f))
            # print('pyfiles1', time() - start)
    n_gpu = setgpu(args.gpu)
    # args.n_gpu = n_gpu
    
    # net = net.cuda()
    
    loss = loss.cpu()
    device = 'cpu'
    net = net.to(device)
    cudnn.benchmark = False #true
    # net = DataParallel(net).cuda()
    # print('net0', time.time() - start)
    traindatadir = config_training['train_preprocess_result_path']#'/home/zhaojie/zhaojie/Lung/data/luna16/LUNA16PROPOCESSPATH/'
    valdatadir = config_training['val_preprocess_result_path']#'/home/zhaojie/zhaojie/Lung/data/luna16/LUNA16PROPOCESSPATH/'
    testdatadir = config_training['test_preprocess_result_path']#'/home/zhaojie/zhaojie/Lung/data/luna16/LUNA16PROPOCESSPATH/'
    trainfilelist = []
    # print('data_path',config_training['train_data_path'])
    for folder in config_training['train_data_path']:
        print('folder',folder)
        for f in os.listdir(folder):
            if f.endswith('.mhd') and f[:-4] not in config_training['black_list']:
                trainfilelist.append(folder.split('/')[-2]+'/'+f[:-4])
    valfilelist = []
    for folder in config_training['val_data_path']:
        for f in os.listdir(folder):
            if f.endswith('.mhd') and f[:-4] not in config_training['black_list']:
                valfilelist.append(folder.split('/')[-2]+'/'+f[:-4])
    testfilelist = []
    for folder in config_training['test_data_path']:
        for f in os.listdir(folder):
            if f.endswith('.mhd') and f[:-4] not in config_training['black_list']:
                testfilelist.append(folder.split('/')[-2]+'/'+f[:-4])
    
    if args.test == 1:
        print('--------test-------------')
        print('len(testfilelist)',len(testfilelist))
    
        print('batch_size',args.batch_size)
        # margin = 32
        margin = 16
        # sidelen = 144
        sidelen = 64
        # sidelen = 208
        import data
        split_comber = SplitComb(sidelen,config['max_stride'],config['stride'],margin,config['pad_value'])
        dataset = data.DataBowl3Detector(
            testdatadir,
            testfilelist,
            config,
            phase='test',
            split_comber=split_comber)
        test_loader = DataLoader(
            dataset,
            batch_size = 1,
            shuffle = False,
            num_workers = args.workers,
            collate_fn = data.collate,
            pin_memory=False)
        iter1, iter2, iter3, iter4 = next(iter(test_loader))
        # print("sample: ", iter1.size())
        # print("lable: ", iter2.size())
        # print("coord: ", iter3.size())
        for i, (data, target, coord, nzhw) in enumerate(test_loader): # check data consistency
            if i >= len(testfilelist)//args.batch_size:
                break
        
        tet(test_loader, net, get_pbb, save_dir,config)
        return

    import data
    print('len(trainfilelist)',len(trainfilelist))
    print('trainfilelist',trainfilelist)
    print('batch_size',args.batch_size)
    dataset = data.DataBowl3Detector(
        traindatadir,
        trainfilelist,
        config,
        phase = 'train')
    print('train_loader')
    train_loader = DataLoader(
        dataset,
        batch_size = args.batch_size,
        shuffle = False,
        num_workers = args.workers,
        pin_memory=False)

    dataset = data.DataBowl3Detector(
        valdatadir,
        valfilelist,
        config,
        phase = 'val')
    print('val_loader')
    val_loader = DataLoader(
        dataset,
        batch_size = args.batch_size,
        shuffle = False,
        num_workers = args.workers,
        pin_memory=True)
    iter1, iter2, iter3 = next(iter(train_loader))
    print("sample: ", iter1.size())
    print("lable: ", iter2.size())
    print("coord: ", iter3.size())
    # for i, (data, target, coord) in enumerate(train_loader): # check data consistency
    #     if i >= len(trainfilelist)//args.batch_size:
    #         break
    #
    # for i, (data, target, coord) in enumerate(val_loader): # check data consistency
    #     if i >= len(valfilelist)//args.batch_size:
    #         break

    optimizer = torch.optim.SGD(
        net.parameters(),
        args.lr,
        momentum = 0.9,
        weight_decay = args.weight_decay)
    
    def get_lr(epoch):
        if epoch <= args.epochs * 1/3: #0.5:
            lr = args.lr
        elif epoch <= args.epochs * 2/3: #0.8:
            lr = 0.1 * args.lr
        elif epoch <= args.epochs * 0.8:
            lr = 0.05 * args.lr
        else:
            lr = 0.01 * args.lr
        return lr
    

    for epoch in range(start_epoch, args.epochs + 1):
        train(train_loader, net, loss, epoch, optimizer, get_lr, args.save_freq, save_dir)
        validate(val_loader, net, loss)
        print('stop')

def train(data_loader, net, loss, epoch, optimizer, get_lr, save_freq, save_dir):
    start_time = time.time()
    
    net.train()
    lr = get_lr(epoch)
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr

    metrics = []  #指标

    for i, (data, target, coord) in enumerate(data_loader):#For循环
        data = Variable(data.cpu(), requires_grad=True) #保存梯度
        target = Variable(target.cpu())
        coord = Variable(coord.cpu(), requires_grad=True)

        output = net(data, coord)
        # print('---------', data.size(),coord.size(),target.size(),output.size())#torch.Size([1, 1, 96, 96, 96]), torch.Size([1, 3, 24, 24, 24]), torch.Size([1, 24, 24, 24, 3, 5]), torch.Size([1, 24, 24, 24, 3, 5]))
        loss_output = loss(output, target)
        optimizer.zero_grad()
        # print('loss_output[0]',loss_output.shape)
        loss_output[0].backward()  #梯度求解
        optimizer.step()

        # loss_output[0] = loss_output[0].data[0]
        loss_output[0] = loss_output[0].item()
        # print('loss_output[1]',loss_output[0])
        
        #metrics.append(loss_output)
        metrics = np.asarray(metrics)
        print('metrics',type(metrics))
    
    if epoch % args.save_freq == 0:            
        state_dict = net.state_dict()
        for key in state_dict.keys():    #存放权重
            state_dict[key] = state_dict[key].cpu()
            
        torch.save({
            'epoch': epoch + 1,
            'save_dir': save_dir,
            'state_dict': state_dict,
            'args': args},
            os.path.join(save_dir, '%03d.ckpt' % epoch))
        print("save model on epoch %d" % epoch)
    end_time = time.time()

    metrics = np.asarray(metrics, dtype=np.float32)
    # print('Epoch %03d (lr %.5f)' % (epoch, lr))
    # print('Tra in:      tpr %3.2f, tnr %3.2f, total pos %d, total neg %d, time %3.2f' % (
    #     100.0 * np.sum(metrics[:, 6]) / np.sum(metrics[:, 7]),
    #     100.0 * np.sum(metrics[:, 8]) / np.sum(metrics[:, 9]),
    #     np.sum(metrics[:, 7]),
    #     np.sum(metrics[:, 9]),
    #     end_time - start_time))
    # print('loss %2.4f, classify loss %2.4f, regress loss %2.4f, %2.4f, %2.4f, %2.4f' % (
    #     np.mean(metrics[:, 0]),
    #     np.mean(metrics[:, 1]),
    #     np.mean(metrics[:, 2]),
    #     np.mean(metrics[:, 3]),
    #     np.mean(metrics[:, 4]),
    #     np.mean(metrics[:, 5])))
    # print

def validate(data_loader, net, loss):
    start_time = time.time()
    
    net.eval()

    metrics = []
    for i, (data, target, coord) in enumerate(data_loader):
        data = Variable(data.cpu())
        target = Variable(target.cpu())
        coord = Variable(coord.cpu())

        output = net(data, coord)
        loss_output = loss(output, target, train = False)
        # print('output',len(output))
        # for numi in range(len(output)):
            # print('-------',output[numi].shape,target[numi].shape)
        # print('target',len(target))
        # loss_output[0] = loss_output[0].data[0]
        loss_output[0] = loss_output[0].item()
        metrics.append(loss_output)    
    end_time = time.time()

    # metrics = np.asarray(metrics, np.float32)
    # print('Validation: tpr %3.2f, tnr %3.8f, total pos %d, total neg %d, t'
    #       'ime %3.2f' % (
    #     100.0 * np.sum(metrics[:, 6]) / np.sum(metrics[:, 7]),
    #     100.0 * np.sum(metrics[:, 8]) / np.sum(metrics[:, 9]),
    #     np.sum(metrics[:, 7]),
    #     np.sum(metrics[:, 9]),
    #     end_time - start_time))
    # print('loss %2.4f, classify loss %2.4f, regress loss %2.4f, %2.4f, %2.4f, %2.4f' % (
    #     np.mean(metrics[:, 0]),
    #     np.mean(metrics[:, 1]),
    #     np.mean(metrics[:, 2]),
    #     np.mean(metrics[:, 3]),
    #     np.mean(metrics[:, 4]),
    #     np.mean(metrics[:, 5])))
    # print
    # print

def tet(data_loader, net, get_pbb, save_dir, config):
    start_time = time.time()
    save_dir = os.path.join(save_dir,'bbox')
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    print(save_dir)
    net.eval()
    namelist = []
    split_comber = data_loader.dataset.split_comber
    for i_name, (data, target, coord, nzhw) in enumerate(data_loader):
        s = time.time()
        target = [np.asarray(t, np.float32) for t in target]
        lbb = target[0]
        nzhw = nzhw[0]
        name = data_loader.dataset.filenames[i_name].split('/')[-1].split('_clean')[0] #.split('-')[0]  wentao change
        data = data[0][0]
        coord = coord[0][0]
        isfeat = False
        # isfeat = True
        if 'output_feature' in config:
            if config['output_feature']:
                isfeat = True
        n_per_run = args.n_test
        print('data.size',data.size(), n_per_run)
        splitlist = range(0,len(data)+1,n_per_run)
        print('splitlist',splitlist)
        if splitlist[-1]!=len(data):
            splitlist.append(len(data))
        outputlist = []
        featurelist = []

        for i in range(len(splitlist)-1):
            input = Variable(data[splitlist[i]:splitlist[i+1]]).cpu
            inputcoord = Variable(coord[splitlist[i]:splitlist[i+1]]).cpu
            # print('input',input.shape[0])
            if isfeat:
                output,feature = net(input(),inputcoord())
                featurelist.append(feature.data.cpu().numpy())
            else:
                output = net(input(),inputcoord())
            outputlist.append(output.data.cpu().numpy())
        
        output = np.concatenate(outputlist,0)
        print('NET-output',output.shape)
        output = split_comber.combine(output,nzhw=nzhw)
        # print('COMBINE-output',output.shape)
        if isfeat:
            feature = np.concatenate(featurelist,0).transpose([0,2,3,4,1])[:,:,:,:,:,np.newaxis]
            feature = split_comber.combine(feature,64)[...,0]

        thresh = args.testthresh # -8 #-3  #应该是阈值？
        # print('pbb thresh', thresh)
        pbb,mask = get_pbb(output,thresh,ismask=True)
        if isfeat:
            feature_selected = feature[mask[0],mask[1],mask[2]]
            np.save(os.path.join(save_dir, name+'_feature.npy'), feature_selected)
        #tp,fp,fn,_ = acc(pbb,lbb,0,0.1,0.1)
        #print([len(tp),len(fp),len(fn)])
        # print([i_name,name])
        # print(mask, isfeat)#[xx,yy,zz,aa]
        e = time.time()
        # print(os.path.join(save_dir, name+'_pbb.npy'))
        np.save(os.path.join(save_dir, name+'_pbb.npy'), pbb)
        np.save(os.path.join(save_dir, name+'_lbb.npy'), lbb)
    np.save(os.path.join(save_dir, 'namelist.npy'), namelist)
    end_time = time.time()


    print('elapsed time is %3.2f seconds' % (end_time - start_time))
    print
    print

def singletest(data,net,config,splitfun,combinefun,n_per_run,margin = 64,isfeat=False):
    z, h, w = data.size(2), data.size(3), data.size(4)
    print(data.size())
    data = splitfun(data,config['max_stride'],margin)
    data = Variable(data.cpu())
    splitlist = range(0,args.split+1,n_per_run)
    outputlist = []
    featurelist = []
    for i in range(len(splitlist)-1):
        if isfeat:
            output,feature = net(data[splitlist[i]:splitlist[i+1]])
            featurelist.append(feature)
        else:
            output = net(data[splitlist[i]:splitlist[i+1]])
        output = output.data.cpu().numpy()
        outputlist.append(output)
        
    output = np.concatenate(outputlist,0)
    output = combinefun(output, z / config['stride'], h / config['stride'], w / config['stride'])
    if isfeat:
        feature = np.concatenate(featurelist,0).transpose([0,2,3,4,1])
        feature = combinefun(feature, z / config['stride'], h / config['stride'], w / config['stride'])
        return output,feature
    else:
        return output
if __name__ == '__main__':
    main()
