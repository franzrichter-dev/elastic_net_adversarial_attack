import argparse
import utils
import adversarial_attack.attack_utils as attack_utils
import json
import torch

def main(dataset, samplesize_accuracy, samplesize_attack, dataset_root, model, model_norm, attack_types, epsilon_l1, epsilon_l2, 
         eps_iter, norm, max_iterations, batchsize, save_images, verbose):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # Load dataset
    xtest, ytest = utils.load_dataset(dataset=dataset, dataset_split=samplesize_accuracy, root=dataset_root)

    # Load model
    net, art_net, fb_net, alias = utils.get_model(dataset=dataset, modelname=model, norm=model_norm)

    # calculate accuracy, select a subset from the correctly classified images
    correct_map = utils.test_accuracy(net, xtest, ytest)
    xtest, ytest = utils.subset(correct_map, xtest, ytest, attack_samples=samplesize_attack)
    # Experiment setup
    Experiment = attack_utils.Experiment_class(
        art_net, fb_net, net, xtest, ytest, alias,
        epsilon_l1=epsilon_l1,
        epsilon_l2=epsilon_l2,
        eps_iter=eps_iter,
        norm=norm,
        max_iterations=max_iterations,
        batchsize=batchsize,
        save_images=save_images,
        verbose=verbose
    )

    # Attack comparison
    results_dict_attack_comparison = Experiment.attack_comparison(attack_types)

    json_file_path = f'./data/attack_comparison_{alias}_{samplesize_attack}samples_l1-epsilon-{epsilon_l1}.json'
    with open(json_file_path, 'w') as f:
        json.dump(results_dict_attack_comparison, f, indent=4)
    print(f'Evaluation results are saved under "{json_file_path}".')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hyperparameter Sweep Script")
    parser.add_argument('--dataset', type=str, default='imagenet', choices=['cifar10', 'imagenet'],
                        help="Dataset to use")
    parser.add_argument('--samplesize_accuracy', type=int, default=10, help="Split size for test accuracy evaluation")
    parser.add_argument('--samplesize_attack', type=int, default=1, help="Split size for attack evaluation")
    parser.add_argument('--dataset_root', type=str, default='../data', help="data folder relative root")
    parser.add_argument('--model', type=str, default='standard',
                        help="Model name (e.g., standard, MainiAVG, etc.)")
    parser.add_argument('--model_norm', type=str, default='Linf',
                        help="Attack Norm the selected model was trained with. Only necessary if you load robustbench models")
    parser.add_argument('--attack_types', type=str, nargs='+',
                        default=['exp_attack_l1',
                                 'original_AutoAttack_apgd_only',
                                 ], 
                        choices=[['fast_gradient_method',
                                'projected_gradient_descent', #batch
                                'pgd_early_stopping',
                                'deep_fool',
                                'brendel_bethge', #batch 
                                'pointwise_blackbox', #batch (+better results ??)
                                'pointwise_blackbox+boundary', #batch
                                'pointwise_blackbox+hopskipjump', #batch
                                'geoda_blackbox',
                                'sparse_rs_blackbox', #batch (+better results ??)
                                'carlini_wagner_l2', #worse in batches
                                'elastic_net', #batch (little advantage)
                                'exp_attack', #worse in batches
                                'exp_attack_smooth',
                                'exp_attack_l1_l2',
                                'auto_projected_gradient_descent',
                                'elastic_net_L1_rule',
                                'elastic_net_L1_rule_higher_beta',
                                'ART_AutoAttack',
                                'original_AutoAttack',
                                'original_AutoAttack_apgd_only',
                                'exp_attack_l1',
                                'custom_apgd']], 
                        help="List of attack types for comparison (space-separated). ")
    parser.add_argument('--epsilon_l1', type=float, default=12, help="L1 norm epsilon (default: 12 for CIFAR10, 75 otherwise)")
    parser.add_argument('--epsilon_l2', type=float, default=0.5, help="L2 norm epsilon")
    parser.add_argument('--eps_iter', type=float, default=0.2, help="Step size for manual iterative attacks")
    parser.add_argument('--attack_norm', type=int, default=1, choices=[1, 2, float('inf')],
                        help="Attack norm type (1, 2, float('inf'))")
    parser.add_argument('--max_iterations', type=int, default=300, help="Maximum iterations for attacks")
    parser.add_argument('--batchsize', type=int, default=1, help="Batchsize to run every adversarial attack on")
    parser.add_argument('--save_images', type=int, default=1, help="Integer > 0: number of saved images per attack, 0: do not save)")
    parser.add_argument('--verbose', type=bool, default=True, help="Verbose output")

    args = parser.parse_args()
    main(
        args.dataset, args.samplesize_accuracy, args.samplesize_attack, args.dataset_root, args.model, args.model_norm, args.attack_types,
        args.epsilon_l1, args.epsilon_l2, args.eps_iter, args.attack_norm, args.max_iterations, args.batchsize, args.save_images, args.verbose
    )