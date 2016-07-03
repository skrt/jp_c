//
//  LiveViewController.swift
//  NewsReader
//
//  Created by skrt on 2016/06/26.
//  Copyright © 2016年 skrt. All rights reserved.
//

import UIKit

class ListViewController: UITableViewController {
    override func tableView(tableView: UITableView, numberOfRowsInSection section: Int) -> Int{
        return 3
    }

    override func tableView(tableView: UITableView, cellForRowAtIndexPath indexPath: NSIndexPath) -> UITableViewCell{
        let cell = tableView.dequeueReusableCellWithIdentifier("Cell", forIndexPath: indexPath)
        return cell
    }
}