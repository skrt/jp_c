//
//  ViewController.swift
//  Test
//
//  Created by skrt on 2016/06/25.
//  Copyright © 2016年 skrt. All rights reserved.
//

import UIKit

class ViewController: UIViewController {


    @IBOutlet weak var label: UILabel!
    @IBAction func slider(sender: UISlider) {
        label.text = "\(sender.value)"
        
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

