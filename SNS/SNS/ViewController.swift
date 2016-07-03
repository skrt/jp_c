//
//  ViewController.swift
//  SNS
//
//  Created by skrt on 2016/06/25.
//  Copyright © 2016年 skrt. All rights reserved.
//

import UIKit

class ViewController: UIViewController {

    @IBOutlet weak var imageView: UIImageView!
    

    @IBAction func showActivityView(sender: UIBarButtonItem) {
        
        let controller = UIActivityViewController(activityItems: [imageView.image!], applicationActivities: nil)
        self.presentViewController(controller, animated: true, completion: {print("表示完了")})
    }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        // Do any additional setup after loading the view, typically from a nib.
    }


    override func didReceiveMemoryWarning() {
        super.didReceiveMemoryWarning()
        // Dispose of any resources that can be recreated.
    }


}

