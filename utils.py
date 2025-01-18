from robustbench.utils import load_model
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
from art.estimators.classification import PyTorchClassifier
import foolbox as fb
import torch.nn.functional as F
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
cuda = True if torch.cuda.is_available() else False
import torch
import torchvision
import torchvision.transforms as transforms

def load_dataset(dataset, dataset_split, root='../data'):

    if dataset== 'imagenet':

        transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Resize(256, antialias=True),
        transforms.CenterCrop(224)
                                    ])
        
        testset = datasets.ImageFolder(root=root+'/ImageNet/val', transform=transform)
        
    elif dataset == 'cifar10':

        transform = transforms.Compose([
        transforms.ToTensor(),
                                    ])
        
        testset = datasets.CIFAR10(root=root+'/cifar', train=False, download=True, transform=transform)

    else: 
        raise KeyError("Dataset not implemented.")
    
    # Truncated testset for experiments and ablations
    if isinstance(dataset_split, int):
        testset, _ = torch.utils.data.random_split(testset,
                                                          [dataset_split, len(testset) - dataset_split],
                                                          generator=torch.Generator().manual_seed(42))
    
    # Extract data and labels from torchvision dataset
    xtest = torch.stack([data[0] for data in testset])
    ytest = torch.tensor([data[1] for data in testset])

    return xtest, ytest

def load_dataset(dataset, dataset_split, root='../data'):

    if dataset== 'imagenet':

        transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Resize(256, antialias=True),
        transforms.CenterCrop(224)
                                    ])
        
        testset = datasets.ImageFolder(root=root+'/ImageNet/val', transform=transform)
        
    elif dataset == 'cifar10':

        transform = transforms.Compose([
        transforms.ToTensor(),
                                    ])
        
        testset = datasets.CIFAR10(root=root+'/cifar', train=False, download=True, transform=transform)

    else: 
        raise KeyError("Dataset not implemented.")
    
    # Truncated testset for experiments and ablations
    if isinstance(dataset_split, int):
        testset, _ = torch.utils.data.random_split(testset,
                                                          [dataset_split, len(testset) - dataset_split],
                                                          generator=torch.Generator().manual_seed(42))
    
    # Extract data and labels from torchvision dataset
    xtest, ytest = zip(*[(data[0], data[1]) for data in testset])
    return torch.stack(xtest), torch.tensor(ytest)

def get_model(dataset, modelname, norm=None):
    
    if modelname=='CroceL1' and dataset=='cifar10': 
        '''
        based on https://github.com/fra31/robust-finetuning
        "Adversarial robustness against multiple and single lp-threat models via quick fine-tuning of robust classifiers", Francesco Croce, Matthias Hein, ICML 2022
        https://arxiv.org/abs/2105.12508
        '''
        from models import fast_models
        net = fast_models.PreActResNet18(10, activation='softplus1', cuda=cuda)
        ckpt = torch.load('./models/pretrained_models/CroceL1.pth', map_location=device)
        net.load_state_dict(ckpt)
    elif modelname in ['MainiMSD', 'MainiAVG'] and dataset == 'cifar10':
        '''
        based on https://github.com/locuslab/robust_union/tree/master/CIFAR10
        "Adversarial Robustness Against the Union of Multiple Perturbation Models", by Pratyush Maini, Eric Wong and Zico Kolter, ICML 2020
        https://arxiv.org/abs/2105.12508
        '''
        from models import preact_resnet
        net = preact_resnet.PreActResNet18()
        ckpt = torch.load(f'./models/pretrained_models/{modelname}.pt', map_location=device)
        net.load_state_dict(ckpt)
    elif modelname in ['standard', 'corruption_robust'] and dataset == 'cifar10':
        from models import wideresnet
        
        if modelname == 'standard':
            net = wideresnet.WideResNet_28_4(10, 'CIFAR10', normalized=True, block=wideresnet.WideBasic, activation_function='relu')
        elif modelname == 'corruption_robust':
            #self trained with massive random data augmentation and JSD consistency loss, but no adversarial objective
            net = wideresnet.WideResNet_28_4(10, 'CIFAR10', normalized=True, block=wideresnet.WideBasic, activation_function='silu')
        model = torch.load(f'./models/pretrained_models/{modelname}.pth', map_location=device)
        state_dict = model["model_state_dict"]
        new_state_dict = {key.replace("module.", ""): value for key, value in state_dict.items()}
        net.load_state_dict(new_state_dict, strict=True)
    elif modelname == 'standard_resnet50' and dataset == 'imagenet':
        from torchvision.models import resnet50, ResNet50_Weights
        net = resnet50(weights=ResNet50_Weights.DEFAULT).to(device)
    else: #robustbench models
        net = load_model(model_name=modelname, dataset=dataset, threat_model=norm) #'Wang2023Better_WRN-28-10'
        modelname = modelname + '_' + norm
        
    #net = torch.nn.DataParallel(net)
    net.eval()

    # Define loss function and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(net.parameters(), lr=0.01)

    if dataset == 'imagenet':
        nb_classes = 1000 
        input_shape=(3, 224, 224)
    elif dataset == 'cifar10':
        nb_classes = 10
        input_shape=(3, 32, 32)
    else: 
        raise KeyError("Dataset not implemented.")

    # Initialize wrappers for ART toolbox and foolbox
    art_net = PyTorchClassifier(model=net,
                               loss=criterion,
                               optimizer=optimizer,
                               input_shape=input_shape,
                               nb_classes=nb_classes,
                               device_type=device,
                               clip_values=(0.0, 1.0))
    fb_net = fb.PyTorchModel(net, bounds=(0.0, 1.0), device=device)

    net.to(device)

    alias = modelname + '_' + dataset

    return net, art_net, fb_net, alias

def test_accuracy(model, xtest, ytest, batch_size=100):
    """
    Tests the accuracy of the model and returns a tensor indicating whether each test sample
    was classified correctly or not.

    Args:
        model: The trained model to test.
        xtest: Test dataset features (as a torch tensor).
        ytest: True labels for the test dataset.
        batch_size: Number of samples per batch for evaluation.

    Returns:
        A tensor of booleans where each element corresponds to whether the classification
        of the respective test sample was correct or not.
    """
    model.eval()
    correct_list = []  # To store correctness of each sample

    with torch.no_grad():
        for i in range(0, len(xtest), batch_size):
            x_batch = xtest[i:i + batch_size].to(device)
            y_batch = ytest[i:i + batch_size].to(device)
            outputs = model(x_batch)
            _, predicted = torch.max(outputs, 1)

            # Append the boolean tensor correctness values
            correct_list.append((predicted == y_batch).cpu())

    # Concatenate all boolean tensors into a single tensor
    correct_tensor = torch.cat(correct_list)

    # Calculate and print the overall accuracy
    accuracy = (correct_tensor.sum().item() / len(correct_tensor)) * 100
    print(f'\nAccuracy of the test set is: {accuracy:.3f}%\n')

    return correct_tensor

def subset(correct_tensor, xtest, attack_samples=100):
    """
    Selects n samples from xtest where the classification was correct.

    Args:
        correct_tensor: Tensor of booleans indicating correctness of classification.
        xtest: Test dataset features (as a torch tensor).
        n: Number of samples to select.

    Returns:
        A subset of xtest containing n correctly classified samples.
    """
    if attack_samples > correct_tensor.sum().item():
        raise ValueError("n cannot be greater than the number of correctly classified samples.")

    # Get indices of correctly classified samples
    correct_indices = torch.nonzero(correct_tensor, as_tuple=True)[0]

    # Select the first n correctly classified samples
    selected_indices = correct_indices[:attack_samples]

    # Return the selected samples from xtest
    return xtest[selected_indices]
